"""
Simple ST -> PLCOpenXML converter tailored to the provided `Logger.st` format.
- Usage: call convert(input_st_path, output_xml_path)
- Produces an XML similar to your working `LoggerRealValues.xml` format.

This is intentionally small and easy to adapt.
"""
import re
import uuid
from pathlib import Path


def uuid_str():
    return str(uuid.uuid4())


def escape_xhtml(s: str) -> str:
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    return s


class Method:
    def __init__(self, name):
        self.name = name
        self.input_vars = []
        self.output_vars = []
        self.local_vars = []
        self.body = ''
        self.object_id = uuid_str()


class Property:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_
        self.local_vars = []
        self.body = ''
        self.attribute = None
        self.object_id = uuid_str()


def parse_st(text: str):
    # Very small parser for the Logger.st structure
    fb_name = re.search(r'FUNCTION_BLOCK\s+(\w+)', text)
    fb_name = fb_name.group(1) if fb_name else 'FB'

    # parse constant block
    consts = {}
    m = re.search(r'VAR\s+CONSTANT\s*(.*?)END_VAR', text, re.S)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip().rstrip(';')
            if not line: continue
            mo = re.match(r"(\w+)\s*:\s*(\w+)\s*:=\s*(.+)", line)
            if mo:
                name, type_, val = mo.groups()
                consts[name] = val.strip()

    # parse top-level VAR block (non-constant) before methods
    vars_block = re.search(r'VAR\s*(.*?)END_VAR', text, re.S)
    vars_ = {}
    if vars_block:
        for line in vars_block.group(1).splitlines():
            line = line.strip().rstrip(';')
            if not line: continue
            mo = re.match(r"(\w+)\s*:\s*(ARRAY\s*\[.*?\]\s*OF\s*\w+|\w+)\s*(?::=\s*(.+))?", line)
            if mo:
                name, type_, init = mo.groups()
                vars_[name] = {'type': type_.strip(), 'init': (init.strip() if init else None)}

    # parse methods
    methods = []
    for mm in re.finditer(r'METHOD\s+PUBLIC\s+(\w+)(.*?)(?=METHOD\s+PUBLIC|PROPERTY\s+PUBLIC|END_FUNCTION_BLOCK)', text, re.S):
        name = mm.group(1)
        block = mm.group(2)
        method = Method(name)
        # inputs
        mi = re.search(r'VAR_INPUT\s*(.*?)END_VAR', block, re.S)
        if mi:
            for line in mi.group(1).splitlines():
                line = line.strip().rstrip(';')
                if not line: continue
                mo = re.match(r"(\w+)\s*:\s*(\w+)", line)
                if mo:
                    method.input_vars.append((mo.group(1), mo.group(2)))
        mo2 = re.search(r'VAR_OUTPUT\s*(.*?)END_VAR', block, re.S)
        if mo2:
            for line in mo2.group(1).splitlines():
                line = line.strip().rstrip(';')
                if not line: continue
                m3 = re.match(r"(\w+)\s*:\s*(\w+)", line)
                if m3:
                    method.output_vars.append((m3.group(1), m3.group(2)))
        ml = re.search(r'VAR\s*(?!_INPUT|_OUTPUT)(.*?)END_VAR', block, re.S)
        if ml:
            for line in ml.group(1).splitlines():
                line = line.strip().rstrip(';')
                if not line: continue
                m4 = re.match(r"(\w+)\s*:\s*(\w+)", line)
                if m4:
                    method.local_vars.append((m4.group(1), m4.group(2)))
        # body between BEGIN and END_METHOD
        mb = re.search(r'BEGIN\s*(.*?)END_METHOD', mm.group(0), re.S)
        if mb:
            method.body = mb.group(1).strip()
        methods.append(method)

    # parse properties
    properties = []
    for pm in re.finditer(r'PROPERTY\s+PUBLIC\s+(\w+)\s*:\s*(\w+)(.*?)END_PROPERTY', text, re.S):
        name = pm.group(1)
        type_ = pm.group(2)
        block = pm.group(3)
        prop = Property(name, type_)
        # attribute pragma
        at = re.search(r"\{attribute\s+['\"](\w+)['\"]\s*:=\s*['\"](\w+)['\"]\}", block)
        if at:
            prop.attribute = (at.group(1), at.group(2))
        # property GET local vars and body
        getm = re.search(r'PROPERTY\s+GET\s*(.*?)END_PROPERTY', pm.group(0), re.S)
        if getm:
            gb = getm.group(1)
            ml = re.search(r'VAR\s*(.*?)END_VAR', gb, re.S)
            if ml:
                for line in ml.group(1).splitlines():
                    line = line.strip().rstrip(';')
                    if not line: continue
                    m4 = re.match(r"(\w+)\s*:\s*(\w+)", line)
                    if m4:
                        prop.local_vars.append((m4.group(1), m4.group(2)))
            # body: between BEGIN and END_PROPERTY
            mb = re.search(r'BEGIN\s*(.*)', gb, re.S)
            if mb:
                # body until END_PROPERTY will be trimmed later
                body = mb.group(1)
                # remove trailing END_PROPERTY if present
                body = re.sub(r'END_PROPERTY\s*$', '', body, flags=re.S).strip()
                prop.body = body
        properties.append(prop)

    return fb_name, consts, vars_, methods, properties


def generate_xml(fb_name, consts, vars_, methods, properties, out_path: Path):
    now = '2026-02-09T22:13:12.1011556'
    fileHeader = f'<fileHeader companyName="" productName="Machine Expert Logic Builder" productVersion="V22.1.1.0" creationDateTime="{now}" />'
    contentHeader = f'''  <contentHeader name="{fb_name}" version="0.0.0.0" modificationDateTime="{now}" author="vboxuser">'''

    # build methods xml
    methods_xml = ''
    for m in methods:
        inp = ''.join([f'<variable name="{n}"><type><{t} /></type></variable>' for n,t in m.input_vars])
        outp = ''.join([f'<variable name="{n}"><type><{t} /></type></variable>' for n,t in m.output_vars])
        local = ''.join([f'<variable name="{n}"><type><{t} /></type></variable>' for n,t in m.local_vars])
        body = escape_xhtml(m.body)
        methods_xml += f'''          <data name="http://www.3s-software.com/plcopenxml/method" handleUnknown="implementation">
            <Method name="{m.name}" ObjectId="{m.object_id}">
              <interface>
                {('<inputVars>' + inp + '</inputVars>') if m.input_vars else ''}
                {('<outputVars>' + outp + '</outputVars>') if m.output_vars else ''}
                {('<localVars>' + local + '</localVars>') if m.local_vars else ''}
              </interface>
              <body>
                <ST>
                  <xhtml xmlns="http://www.w3.org/1999/xhtml">{body}</xhtml>
                </ST>
              </body>
              <addData />
            </Method>
          </data>\n'''

    # build properties xml
    props_xml = ''
    for p in properties:
        local = ''.join([f'<variable name="{n}"><type><{t} /></type></variable>' for n,t in p.local_vars])
        body = escape_xhtml(p.body)
        attr_xml = ''
        if p.attribute:
            attr_xml = f'''                  <addData>
                    <data name="http://www.3s-software.com/plcopenxml/attributes" handleUnknown="implementation">
                      <Attributes>
                        <Attribute Name="{p.attribute[0]}" Value="{p.attribute[1]}" />
                      </Attributes>
                    </data>
                  </addData>'''
        props_xml += f'''          <data name="http://www.3s-software.com/plcopenxml/property" handleUnknown="implementation">
            <Property name="{p.name}" ObjectId="{p.object_id}">
              <interface>
                <returnType>
                  <{p.type} />
                </returnType>
              </interface>
              <GetAccessor>
                <interface>
                  {('<localVars>' + local + '</localVars>') if p.local_vars else ''}
{attr_xml}
                </interface>
                <body>
                  <ST>
                    <xhtml xmlns="http://www.w3.org/1999/xhtml">{body}</xhtml>
                  </ST>
                </body>
                <addData />
              </GetAccessor>
              <addData />
            </Property>
          </data>\n'''

    # assemble final xml
    xml = f'<?xml version="1.0" encoding="utf-8"?>\n<project xmlns="http://www.plcopen.org/xml/tc6_0200">\n  {fileHeader}\n{contentHeader}\n    <coordinateInfo>\n      <fbd>\n        <scaling x="1" y="1" />\n      </fbd>\n      <ld>\n        <scaling x="1" y="1" />\n      </ld>\n      <sfc>\n        <scaling x="1" y="1" />\n      </sfc>\n    </coordinateInfo>\n    <addData>\n      <data name="http://www.3s-software.com/plcopenxml/projectinformation" handleUnknown="implementation">\n        <ProjectInformation>\n          <property name="Author" type="string">vboxuser</property>\n          <property name="Company" type="string" />\n          <property name="Description" type="string" />\n          <property name="Git:IsGitManaged" type="boolean">false</property>\n          <property name="Project" type="string">{fb_name}</property>\n          <property name="Svn:IsSvnManaged" type="boolean">false</property>\n          <property name="Title" type="string">{fb_name}</property>\n          <property name="Version" type="version">0.0.0.0</property>\n        </ProjectInformation>\n      </data>\n    </addData>\n  </contentHeader>\n  <types>\n    <dataTypes />\n    <pous>\n      <pou name="{fb_name}" pouType="functionBlock">\n        <interface>\n          <localVars constant="true">\n            <variable name="cArrSize">\n              <type>\n                <INT />\n              </type>\n              <initialValue>\n                <simpleValue value="{consts.get('cArrSize','100')}" />\n              </initialValue>\n            </variable>\n          </localVars>\n          <localVars>\n            '"""
    # We'll keep original 'values' and 'count' declarations if present in vars_
    xml += """
            <variable name="values">\n              <type>\n                <array>\n                  <dimension lower="1" upper="cArrSize" />\n                  <baseType>\n                    <REAL />\n                  </baseType>\n                </array>\n              </type>\n            </variable>\n            <variable name="count">\n              <type>\n                <INT />\n              </type>\n              <initialValue>\n                <simpleValue value="0" />\n              </initialValue>\n            </variable>\n          </localVars>\n        </interface>\n        <body>\n          <ST>\n            <xhtml xmlns="http://www.w3.org/1999/xhtml" />\n          </ST>\n        </body>\n        <addData>\n"""
    xml += methods_xml
    xml += props_xml
    xml += """        <data name="http://www.3s-software.com/plcopenxml/objectid" handleUnknown="discard">\n            <ObjectId>""" + uuid_str() + """</ObjectId>\n          </data>\n        </addData>\n      </pou>\n    </pous>\n  </types>\n  <instances>\n    <configurations />\n  </instances>\n  <addData>\n    """
    # Project structure
    proj_struct = '    <data name="http://www.3s-software.com/plcopenxml/projectstructure" handleUnknown="discard">\n      <ProjectStructure>\n        <Object Name="' + fb_name + '" ObjectId="' + uuid_str() + '">\n'
    # Add methods and properties to project structure
    for m in methods:
        proj_struct += f'          <Object Name="{m.name}" ObjectId="{m.object_id}" />\n'
    for p in properties:
        proj_struct += f'          <Object Name="{p.name}" ObjectId="{p.object_id}" />\n'
    proj_struct += '        </Object>\n      </ProjectStructure>\n    </data>\n  </addData>\n</project>\n'

    xml += proj_struct

    out_path.write_text(xml, encoding='utf-8')
    return out_path


def convert(input_st='Logger.st', output_xml='Logger.generated.xml'):
    p = Path(input_st)
    if not p.exists():
        raise FileNotFoundError(input_st)
    text = p.read_text(encoding='utf-8')
    fb_name, consts, vars_, methods, properties = parse_st(text)
    out = generate_xml(fb_name, consts, vars_, methods, properties, Path(output_xml))
    print('Wrote', out)


if __name__ == '__main__':
    convert()
