from typing import Any, List
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, Context, step, Event
from llama_index.core.llms import ChatMessage
from llama_index.core.tools import  ToolSelection
from llama_index.core.tools.types import BaseTool
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.llms.openai import OpenAI
from llama_index.core.llms.structured_llm import StructuredLLM
from app.services.report_generation.output_renderer import ReportOutput
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.memory import ChatMemoryBuffer

import os
import json
from dotenv import load_dotenv

load_dotenv()

PHOENIX_API_KEY = os.getenv("PHOENENIX_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

report_gen_prompt = json.load(open("app/data/prompts.json", "r"))["REPORT_GENERATION_PROMPT"]

# Set up workflow
class InputEvent(Event):
    input: List[ChatMessage]


class ChunkRetrievalEvent(Event):
    tool_call: ToolSelection


class DocRetrievalEvent(Event):
    tool_call: ToolSelection


class ReportGenerationEvent(Event):
    pass


class ReportGenerationAgent(Workflow):
    """Report generation agent."""

    def __init__(
        self,
        chunk_retriever_tool: BaseTool,
        doc_retriever_tool: BaseTool,
        llm: FunctionCallingLLM | None = None,
        report_gen_sllm: StructuredLLM | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.chunk_retriever_tool = chunk_retriever_tool
        self.doc_retriever_tool = doc_retriever_tool

        self.llm = llm or OpenAI(timeout=120, api_key=OPENAI_KEY, model=OPENAI_MODEL)
        self.summarizer = CompactAndRefine(llm=self.llm)
        assert self.llm.metadata.is_function_calling_model

        self.report_gen_sllm = report_gen_sllm or self.llm.as_structured_llm(
            ReportOutput, system_prompt=report_gen_prompt
        )
        self.report_gen_summarizer = CompactAndRefine(llm=self.report_gen_sllm)

        self.memory = ChatMemoryBuffer.from_defaults(llm=llm)
        self.sources = []

    @step(pass_context=True)
    async def prepare_chat_history(self, ctx: Context, ev: StartEvent) -> InputEvent:
        # clear sources
        self.sources = []

        ctx.data["stored_chunks"] = []
        ctx.data["query"] = ev.input

        # get user input
        user_input = ev.input
        user_msg = ChatMessage(role="user", content=user_input)
        self.memory.put(user_msg)

        # get chat history
        chat_history = self.memory.get()
        return InputEvent(input=chat_history)

    @step(pass_context=True)
    async def handle_llm_input(
        self, ctx: Context, ev: InputEvent
    ) -> ChunkRetrievalEvent | DocRetrievalEvent | ReportGenerationEvent | StopEvent:
        chat_history = ev.input

        response = await self.llm.achat_with_tools(
            [self.chunk_retriever_tool, self.doc_retriever_tool],
            chat_history=chat_history,
        )
        self.memory.put(response.message)

        tool_calls = self.llm.get_tool_calls_from_response(
            response, error_on_no_tool_call=False
        )

        if not tool_calls:
            # all the content should be stored in the context, so just pass along input
            return ReportGenerationEvent(input=ev.input)

        for tool_call in tool_calls:
            if tool_call.tool_name == self.chunk_retriever_tool.metadata.name:
                return ChunkRetrievalEvent(tool_call=tool_call)
            elif tool_call.tool_name == self.doc_retriever_tool.metadata.name:
                return DocRetrievalEvent(tool_call=tool_call)
            else:
                return StopEvent(result={"response": "Invalid tool."})

    @step(pass_context=True)
    async def handle_retrieval(
        self, ctx: Context, ev: ChunkRetrievalEvent | DocRetrievalEvent
    ) -> InputEvent:
        """Handle retrieval.

        Store retrieved chunks, and go back to agent reasoning loop.

        """
        query = ev.tool_call.tool_kwargs["query"]
        if isinstance(ev, ChunkRetrievalEvent):
            retrieved_chunks = self.chunk_retriever_tool(query).raw_output
        else:
            retrieved_chunks = self.doc_retriever_tool(query).raw_output
        ctx.data["stored_chunks"].extend(retrieved_chunks)

        # synthesize an answer given the query to return to the LLM.
        response = self.summarizer.synthesize(query, nodes=retrieved_chunks)
        self.memory.put(
            ChatMessage(
                role="tool",
                content=str(response),
                additional_kwargs={
                    "tool_call_id": ev.tool_call.tool_id,
                    "name": ev.tool_call.tool_name,
                },
            )
        )

        # send input event back with updated chat history
        return InputEvent(input=self.memory.get())

    @step(pass_context=True)
    async def generate_report(
        self, ctx: Context, ev: ReportGenerationEvent
    ) -> StopEvent:
        """Generate report."""
        # given all the context, generate query
        response = self.report_gen_summarizer.synthesize(
            ctx.data["query"], nodes=ctx.data["stored_chunks"]
        )

        return StopEvent(result={"response": response})
