#!/usr/bin/env python3
"""
ST -> PLCOpenXML (tc6_0200) Converter for CODESYS.

Converts Structured Text .st files (IEC 61131-3) to PLCOpenXML format
suitable for importing into CODESYS Machine Expert Logic Builder.

This is a compact, robust implementation that supports:
- FUNCTION_BLOCK parsing (variables, constants, fb init code)
- METHOD parsing (VAR_INPUT/OUTPUT/local, bodies)
- PROPERTY parsing (GET accessors, pragmas)
- ARRAY types with dimensions
- Optional custom END_BEGIN marker to terminate BEGIN sections

Usage:
  python st_to_plcopenxml.py <input.st> <output.xml>

Author: Assistant
"""

import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def uuid_str() -> str:
    return str(uuid.uuid4())


def escape_xhtml(s: str) -> str:
    if s is None:
        return ''
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    return s


def compact_body(s: str) -> str:
    if not s:
        return ''
    # Remove common leading indentation from each line and strip outer blank lines
    lines = s.splitlines()
    # remove leading/trailing blank lines
    while lines and lines[0].strip() == '':
        lines.pop(0)
    while lines and lines[-1].strip() == '':
        lines.pop()
    # left-strip each line to avoid extra indentation introduced by pretty printers
    lines = [ln.lstrip() for ln in lines]
    return '\n'.join(lines).strip()


class Variable:
    def __init__(self, name: str, type_str: str, init_val: Optional[str] = None):
        self.name = name
        self.type_str = type_str
        self.init_val = init_val

    def __repr__(self):
        return f"Variable({self.name}: {self.type_str})"


class Method:
    def __init__(self, name: str):
        self.name = name
        self.input_vars: List[Tuple[str, str]] = []
        self.output_vars: List[Tuple[str, str]] = []
        self.local_vars: List[Tuple[str, str]] = []
        self.body = ''
        self.object_id = uuid_str()

    def __repr__(self):
        return f"Method({self.name})"


class Property:
    def __init__(self, name: str, type_str: str):
        self.name = name
        self.type_str = type_str
        self.local_vars: List[Tuple[str, str]] = []
        self.body = ''
        self.attribute: Optional[Tuple[str, str]] = None
        self.object_id = uuid_str()

    def __repr__(self):
        return f"Property({self.name}: {self.type_str})"


class STConverter:
    def __init__(self):
        self.fb_name = 'FB'
        self.fb_body = ''
        self.constants: Dict[str, Variable] = {}
        self.variables: Dict[str, Variable] = {}
        self.methods: List[Method] = []
        self.properties: List[Property] = []

    # ------------------ Parsing helpers ------------------
    def parse_variable_decl(self, name: str, type_str: str, init_val: Optional[str] = None) -> Variable:
        return Variable(name, type_str.strip(), init_val)

    def _parse_var_block(self, block_text: str, is_constant: bool) -> None:
        target = self.constants if is_constant else self.variables
        lines = block_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip().rstrip(';')
            if not line or line.startswith('(*') or line.startswith('//'):
                i += 1
                continue
            m = re.match(r'(\w+)\s*:\s*(.+?)(?:\s*:=\s*(.+))?$', line)
            if m:
                name = m.group(1)
                type_str = m.group(2).strip()
                init_val = m.group(3).strip() if m.group(3) else None
                # gather multiline ARRAY definitions
                if 'ARRAY' in type_str.upper() and 'OF' not in type_str.upper():
                    j = i + 1
                    while j < len(lines):
                        nl = lines[j].strip().rstrip(';')
                        type_str += ' ' + nl
                        if 'OF' in nl.upper():
                            i = j
                            break
                        j += 1
                target[name] = self.parse_variable_decl(name, type_str, init_val)
            i += 1

    def _parse_param_section(self, section_text: str, target_list: List[Tuple[str, str]]) -> None:
        lines = section_text.split('\n')
        for line in lines:
            line = line.strip().rstrip(';')
            if not line or line.startswith('(*') or line.startswith('//'):
                continue
            m = re.match(r'(\w+)\s*:\s*(.+)$', line)
            if m:
                target_list.append((m.group(1), m.group(2).strip()))

    # ------------------ Main parse ------------------
    def parse_st(self, text: str) -> None:
        # fb name
        m = re.search(r'FUNCTION_BLOCK\s+(\w+)', text)
        if m:
            self.fb_name = m.group(1)

        # fb initialization code: BEGIN ... up to METHOD/END_FUNCTION_BLOCK/END_BEGIN
        fb_init = re.search(r'FUNCTION_BLOCK\s+\w+.*?(?:END_VAR)\s*BEGIN\s*(.*?)(?=\s*METHOD|END_FUNCTION_BLOCK|END_BEGIN)', text, re.DOTALL)
        if fb_init:
            self.fb_body = fb_init.group(1).strip()

        # constants
        const_match = re.search(r'VAR\s+CONSTANT\s*\n(.*?)\nEND_VAR', text, re.DOTALL | re.MULTILINE)
        if const_match:
            self._parse_var_block(const_match.group(1), True)

        # member vars (first VAR before methods)
        fb_sec = re.search(r'FUNCTION_BLOCK\s+\w+(.*?)METHOD\s+PUBLIC', text, re.DOTALL)
        if fb_sec:
            var_block = re.search(r'VAR\s*(.*?)END_VAR', fb_sec.group(1), re.DOTALL)
            if var_block:
                self._parse_var_block(var_block.group(1), False)

        # methods
        for mm in re.finditer(r'METHOD\s+PUBLIC\s+(\w+)(.*?)(?=METHOD\s+PUBLIC|PROPERTY\s+PUBLIC|END_FUNCTION_BLOCK)', text, re.DOTALL):
            name = mm.group(1)
            block = mm.group(2)
            method = Method(name)
            # params
            inp = re.search(r'VAR_INPUT\s*(.*?)\s*END_VAR', block, re.DOTALL)
            if inp:
                self._parse_param_section(inp.group(1), method.input_vars)
            out = re.search(r'VAR_OUTPUT\s*(.*?)\s*END_VAR', block, re.DOTALL)
            if out:
                self._parse_param_section(out.group(1), method.output_vars)
            loc = re.search(r'VAR\s*(.*?)\s*END_VAR', block, re.DOTALL)
            if loc:
                self._parse_param_section(loc.group(1), method.local_vars)
            # body: BEGIN ... END_METHOD or END_BEGIN, or code then END_METHOD
            body = re.search(r'BEGIN\s*(.*?)(?:END_METHOD|END_BEGIN)', block, re.DOTALL)
            if body:
                method.body = body.group(1).strip()
            else:
                cleaned = re.sub(r'(VAR_INPUT|VAR_OUTPUT|VAR)\s*.*?END_VAR\s*', '', block, flags=re.DOTALL)
                b2 = re.search(r'(.*?)\s*(?:END_METHOD|END_BEGIN)', cleaned, re.DOTALL)
                if b2:
                    method.body = b2.group(1).strip()
            self.methods.append(method)

        # properties
        for pm in re.finditer(r'PROPERTY\s+PUBLIC\s+(\w+)\s*:\s*(\w+)(.*?)END_PROPERTY', text, re.DOTALL):
            pname = pm.group(1)
            ptype = pm.group(2)
            pblock = pm.group(3)
            prop = Property(pname, ptype)
            # attribute pragma
            a = re.search(r"\{attribute\s+['\"](\w+)['\"]\s*:=\s*['\"](\w+)['\"]\}", pblock)
            if a:
                prop.attribute = (a.group(1), a.group(2))
            # local vars
            loc = re.search(r'VAR\s*(.*?)\s*END_VAR', pblock, re.DOTALL)
            if loc:
                self._parse_param_section(loc.group(1), prop.local_vars)
            # body
            pb = re.search(r'BEGIN\s*(.*?)(?:END_PROPERTY|END_BEGIN)', pblock, re.DOTALL)
            if pb:
                prop.body = pb.group(1).strip()
            else:
                cleaned = re.sub(r'VAR\s*.*?END_VAR\s*', '', pblock, flags=re.DOTALL)
                pb2 = re.search(r'(.*?)(?:END_PROPERTY|END_BEGIN)', cleaned, re.DOTALL)
                if pb2:
                    prop.body = pb2.group(1).strip()
            self.properties.append(prop)

    # ------------------ XML generation ------------------
    def type_to_xml_element(self, type_str: str) -> str:
        t = type_str.strip().rstrip(';')
        if 'ARRAY' in t.upper():
            m = re.match(r'ARRAY\s*\[(.*?)\]\s*OF\s*([^\s;]+)', t, re.IGNORECASE)
            if m:
                dim = m.group(1).strip()
                bt = m.group(2).strip()
                dm = re.match(r'(\d+)\s*\.\.\s*(\d+)', dim)
                if dm:
                    return f'<array><dimension lower="{dm.group(1)}" upper="{dm.group(2)}" /><baseType><{bt} /></baseType></array>'
                return f'<array><dimension>{escape_xhtml(dim)}</dimension><baseType><{bt} /></baseType></array>'
            return '<array><dimension lower="1" upper="100" /><baseType><INT /></baseType></array>'
        # simple
        return f'<{t} />'

    def _generate_methods_xml(self) -> str:
        xml = ''
        for m in self.methods:
            input_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>' for n, t in m.input_vars])
            output_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>' for n, t in m.output_vars])
            local_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>' for n, t in m.local_vars])
            body = escape_xhtml(compact_body(m.body))
            input_section = f'<inputVars>{input_vars}</inputVars>' if m.input_vars else ''
            output_section = f'<outputVars>{output_vars}</outputVars>' if m.output_vars else ''
            local_section = f'<localVars>{local_vars}</localVars>' if m.local_vars else ''
            xml += f'''          <data name="http://www.3s-software.com/plcopenxml/method" handleUnknown="implementation">
            <Method name="{m.name}" ObjectId="{m.object_id}">
              <interface>
                {input_section}
                {output_section}
                {local_section}
              </interface>
              <body>
                <ST>
                  <xhtml xmlns="http://www.w3.org/1999/xhtml">{body}</xhtml>
                </ST>
              </body>
              <addData />
            </Method>
          </data>
'''
        return xml

    def _generate_properties_xml(self) -> str:
        xml = ''
        for p in self.properties:
            retval = f'<returnType>\n                  <{p.type_str} />\n                </returnType>' if p.type_str else ''
            attr_xml = ''
            if p.attribute:
                attr_xml = f'''\n                  <addData>\n                    <data name="http://www.3s-software.com/plcopenxml/attributes" handleUnknown="implementation">\n                      <Attributes>\n                        <Attribute Name="{p.attribute[0]}" Value="{p.attribute[1]}" />\n                      </Attributes>\n                    </data>\n                  </addData>'''
            body = escape_xhtml(compact_body(p.body))
            xml += f'''          <data name="http://www.3s-software.com/plcopenxml/property" handleUnknown="implementation">
            <Property name="{p.name}" ObjectId="{p.object_id}">
              <interface>
                {retval}
              </interface>
              <GetAccessor>
                <interface>{attr_xml}\n                </interface>
                <body>
                  <ST>
                    <xhtml xmlns="http://www.w3.org/1999/xhtml">{body}</xhtml>
                  </ST>
                </body>
                <addData />
              </GetAccessor>
              <addData />
            </Property>
          </data>
'''
        return xml

    def generate_xml(self, output_path: Path) -> Path:
        now = '2026-02-10T00:00:00.0000000'
        project_obj_id = uuid_str()

        member_vars_const = ''
        member_vars_regular = ''
        for v in self.constants.values():
            t = self.type_to_xml_element(v.type_str)
            init_xml = f'<initialValue><simpleValue value="{v.init_val or "0"}" /></initialValue>' if v.init_val else ''
            member_vars_const += f'            <variable name="{v.name}">\n              <type>\n                {t}\n              </type>\n              {init_xml}\n            </variable>\n'
        for v in self.variables.values():
            t = self.type_to_xml_element(v.type_str)
            init_xml = f'<initialValue><simpleValue value="{v.init_val or "0"}" /></initialValue>' if v.init_val else ''
            member_vars_regular += f'            <variable name="{v.name}">\n              <type>\n                {t}\n              </type>\n              {init_xml}\n            </variable>\n'

        methods_xml = self._generate_methods_xml()
        props_xml = self._generate_properties_xml()

        proj_struct = [f'        <Object Name="{m.name}" ObjectId="{m.object_id}" />' for m in self.methods]
        proj_struct += [f'        <Object Name="{p.name}" ObjectId="{p.object_id}" />' for p in self.properties]
        proj_struct_str = '\n'.join(proj_struct)

        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0200">
  <fileHeader companyName="" productName="Machine Expert Logic Builder" productVersion="V22.1.1.0" creationDateTime="{now}" />
  <contentHeader name="{self.fb_name}" version="0.0.0.0" modificationDateTime="{now}" author="vboxuser">
    <coordinateInfo>
      <fbd>
        <scaling x="1" y="1" />
      </fbd>
      <ld>
        <scaling x="1" y="1" />
      </ld>
      <sfc>
        <scaling x="1" y="1" />
      </sfc>
    </coordinateInfo>
    <addData>
      <data name="http://www.3s-software.com/plcopenxml/projectinformation" handleUnknown="implementation">
        <ProjectInformation>
          <property name="Author" type="string">vboxuser</property>
          <property name="Company" type="string" />
          <property name="Description" type="string" />
          <property name="Git:IsGitManaged" type="boolean">false</property>
          <property name="Project" type="string">{self.fb_name}</property>
          <property name="Svn:IsSvnManaged" type="boolean">false</property>
          <property name="Title" type="string">{self.fb_name}</property>
          <property name="Version" type="version">0.0.0.0</property>
        </ProjectInformation>
      </data>
    </addData>
  </contentHeader>
  <types>
    <dataTypes />
    <pous>
      <pou name="{self.fb_name}" pouType="functionBlock">
        <interface>
{('          <localVars constant="true">' + member_vars_const + '          </localVars>' if member_vars_const else '')}
{('          <localVars>' + member_vars_regular + '          </localVars>' if member_vars_regular else '')}
        </interface>
        <body>
          <ST>
            <xhtml xmlns="http://www.w3.org/1999/xhtml">{escape_xhtml(compact_body(self.fb_body))}</xhtml>
          </ST>
        </body>
        <addData>
{methods_xml}{props_xml}        <data name="http://www.3s-software.com/plcopenxml/objectid" handleUnknown="discard">
            <ObjectId>{project_obj_id}</ObjectId>
          </data>
        </addData>
      </pou>
    </pous>
  </types>
  <instances>
    <configurations />
  </instances>
  <addData>
    <data name="http://www.3s-software.com/plcopenxml/projectstructure" handleUnknown="discard">
      <ProjectStructure>
        <Object Name="{self.fb_name}" ObjectId="{project_obj_id}">
{proj_struct_str}
        </Object>
      </ProjectStructure>
    </data>
  </addData>
</project>
'''
        # Try to pretty-print the XML for consistent indentation. If that fails,
        # fall back to writing the raw XML string.
        try:
          from xml.dom import minidom
            parsed = minidom.parseString(xml.encode('utf-8'))
            pretty_bytes = parsed.toprettyxml(indent="  ", encoding='utf-8')
            # Decode and collapse multiple blank lines to a single blank line
            pretty_str = pretty_bytes.decode('utf-8')
            pretty_str = re.sub(r"\n\s*\n+", "\n\n", pretty_str)
            output_path.write_text(pretty_str, encoding='utf-8')
        except Exception:
          output_path.write_text(xml, encoding='utf-8')
        return output_path

    def convert(self, input_st: str, output_xml: str) -> Path:
        input_path = Path(input_st)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_st}")
        text = input_path.read_text(encoding='utf-8')
        self.parse_st(text)
        output_path = Path(output_xml)
        self.generate_xml(output_path)
        print(f'[OK] Converted {input_st} to {output_xml}')
        print(f'  Function Block: {self.fb_name}')
        print(f'  Methods: {len(self.methods)}, Properties: {len(self.properties)}')
        print(f'  Variables: {len(self.variables)}, Constants: {len(self.constants)}')
        return output_path


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python st_to_plcopenxml.py <input.st> <output.xml>')
        sys.exit(1)
    conv = STConverter()
    conv.convert(sys.argv[1], sys.argv[2])
