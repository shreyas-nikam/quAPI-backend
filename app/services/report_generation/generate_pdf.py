import os
import markdown2
import pdfkit
import jinja2
from weasyprint import HTML, CSS
import yaml
from typing import Dict, Any

class MarkdownPDFConverter:
    def __init__(self, template_dir='templates'):
        """
        Initialize the Markdown to PDF converter
        
        :param template_dir: Directory containing template configuration files
        """
        self.template_dir = template_dir
        self.templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Load all template configurations from YAML files
        
        :return: Dictionary of template configurations
        """
        templates = {}
        for filename in os.listdir(self.template_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                with open(os.path.join(self.template_dir, filename), 'r') as f:
                    template_name = os.path.splitext(filename)[0]
                    templates[template_name] = yaml.safe_load(f)
        return templates
    
    def _generate_html(self, markdown_content: str, template_config: Dict[str, Any]) -> str:
        """
        Convert Markdown to HTML with template styling
        
        :param markdown_content: Markdown text to convert
        :param template_config: Template configuration dictionary
        :return: HTML string with applied styling
        """
        # Convert markdown to HTML
        html_content = markdown2.markdown(markdown_content, extras=['tables', 'fenced-code-blocks'])
        
        # Create Jinja2 template for styling and layout
        template_str = """
        <!DOCTYPE html>
<html>
<head>
    <style>
        {{ styles }}
        @page {
            size: A4;
            margin: 1cm;
            @bottom-right {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 12px;
                color: #666;
            }
           
            @bottom-left {
                content: "QuantUniversity | © 2024 | https://www.quantuniversity.com";
                font-size: 12px;
                color: #666;
            }
        }
        .footer {
            position: absolute;
            bottom: 10px;
            left: 10px;
            font-size: 12px;
            color: #666;
        }
        .footer a {
            text-decoration: none;
            color: #0073e6; /* Blue link color */
        }
    </style>
</head>
<body>
    <div class="document">
        <div class="content">
            {{ content }}
        </div>
    </div>
</body>
</html>

        """
        
        template = jinja2.Template(template_str)
        
        # Render the template
        html = template.render(
            content=html_content, 
            config=template_config, 
            styles=template_config.get('css', '')
        )
        
        return html

    
    def convert(self, markdown_path: str, template_name: str, output_path: str = None):
        """
        Convert Markdown file to PDF using specified template
        
        :param markdown_path: Path to the markdown file
        :param template_name: Name of the template to use
        :param output_path: Optional output PDF path
        """
        # Validate template
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Read markdown content
        with open(markdown_path, 'r') as f:
            markdown_content = f.read()
        
        # Get template configuration
        template_config = self.templates[template_name]
        
        # Generate HTML
        html_content = self._generate_html(markdown_content, template_config)
        
        # Generate PDF
        if not output_path:
            output_path = os.path.splitext(markdown_path)[0] + '.pdf'
        
        HTML(string=html_content).write_pdf(
            output_path, 
            stylesheets=[CSS(string=template_config.get('css', ''))]
        )
        
        return output_path

# Example usage
if __name__ == '__main__':
    converter = MarkdownPDFConverter()
    
    # academic
    output = converter.convert(
        markdown_path='document.md', 
        template_name='academic', #technical, business, whitepaper, presentation
        output_path='output-academic.pdf'
    )

    