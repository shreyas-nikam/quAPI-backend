import requests
import json
from types import SimpleNamespace

# prod server
SERVER_URL = "https://api.quantuniversity.com"

class ReportGenerator:
    def __init__(self, name="test", version="1.0", category="basic", notes=[], references=""):
        self.parameters = {}
        self.parameters['name']= name
        self.parameters['version']= version
        if references:
          self.parameters['references']= references
        self.category = category
        self.detail = {}
        self.notes = []
        for note in notes:
            self.notes.append(note.__dict__)
        
    def load(self, value={}):
        if isinstance(value, (dict, str)):
            self.detail = value
        else:
            # self.detail = json.loads(json.dumps(value, default=lambda o: o.__dict__))
            self.detail = value.value
            
    def add_note(self, note):
        self.notes.append(note.__dict__)
    
    def generate(self):
        url = SERVER_URL + "/experiment/public/stage/" + self.category + "/artifact/"
        body = {
            "report_parameters": self.parameters,
            "report_details": self.detail,
            "notes": self.notes
        }
        print(json.dumps(body, indent=4, sort_keys=True))
        response = requests.post(url, json.dumps(body))
        if response.status_code != 200:
            raise ValueError('Unexpected happened.')
        self.report = response.json()['HTML']
        return self.report
    
    def save(self, path="audit.html"):
        file = open(path, "w")
        file.write(self.report)
        print("report is saved to " + file.name)
        file.close()
        try:
            from google.colab import files
            files.download(path)
        except:
            pass
    
    def publish(self, APIkey="", experiment="", stage=""):
        print("Publish reports to QuSandbox available with prime version, contact info@qusandbox.com for more infomation")
    
    
class TemplateReader:
    def __init__(self, template_id="7acd5c69079946b199c8bab692512f27"):
        self.template_id = template_id
        
    def load(self):
        url = SERVER_URL + "/template/" + self.template_id
        response = requests.get(url)
        self.template = response.json()['Items'][0]
        
    def get_raw_json(self):
        return json.loads(self.template['templateValue'])
    
    def get_sample_input(self):
        survey_json = json.loads(self.template['templateValue'])
        sample_input = {}
        for page in survey_json['pages']:
            for element in page['elements']:
                if element['type'] == 'panel':
                    for question in element['elements']:
                        if question["type"] == "rating":
                            sample_input[question['name']] = 4
                        elif question["type"] == "text":
                            sample_input[question['name']] = question['defaultValue']
                        else:
                            sample_input[question['name']] = "TBD"
                else:
                    sample_input[element['name']] = "TBD"
        # return json.loads(json.dumps(sample_input), object_hook=lambda d: SimpleNamespace(**d))
        return TemplateValue(sample_input)
    
class Note:
    categories = ['plotly_json', 'plotly_chart', 'embed', 'link', 'base64', 'file']
    def __init__(self, category="base64", value="", title="", description=""):
        self.Title = title
        self.Content = description
        if category not in self.categories:
            print('Support categories are ' + str(self.categories))
            raise ValueError('Not a support note category')
        else:
            if category in ['link', 'base64', 'file']:
                self.ArtifactType = 'base64'
                if category == 'file':
                    import base64
                    data = open(value, "r").read()
                    self.Artifact = "data:image/jpeg;base64," + base64.b64encode(data).decode('utf-8')
                else:
                    self.Artifact = value
            elif category == 'embed':
                self.ArtifactType = 'embed'
                self.Artifact = value
            elif category in ['plotly_json', 'plotly_chart']:
                import plotly
                self.ArtifactType = 'plotly'
                if category == 'plotly_chart':
                    self.Artifact = plotly.io.to_json(value)
                else:
                    self.Artifact = value

class TemplateValue:
    def __init__(self, input={}):
        self.value = input

    def set_value(self, key, value):
        self.value[key] = value

    def delete_value(self, key):
        if key in self.value:
          del self.value[key]

    def __repr__(self):
        return json.dumps(self.value)

    def __str__(self):
        return json.dumps(self.value)

def browse_all_templates():
    url = SERVER_URL + "/template/"
    response = requests.get(url)
    results = response.json()['Items']
    templates = []
    for result in results:
        templates.append({
            "id":result["SK"].split('#')[1],
            "name":result["templateName"],
            "sample":result["templateSample"],
            "category":result["templateType"]
        })
    return templates

def get_sample(url):
    return requests.get(url).text

def show_report(html):
    try:
        from IPython.core.display import HTML
        display(HTML(html))
    except:
        print('Not in notebook environment, please copy the html string to a file manually')