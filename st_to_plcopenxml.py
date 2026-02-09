#!/usr/bin/env python3
"""
ST -> PLCOpenXML (tc6_0200) Converter for CODESYS.

Converts Structured Text .st files (IEC 61131-3) to PLCOpenXML format 
suitable for importing into CODESYS Machine Expert Logic Builder.

Features:
  - Parses FUNCTION_BLOCK with methods, properties, variables, and constants
  - Handles ARRAY, REAL, INT, BOOL, and other basic types
  - Preserves attribute pragmas on properties {attribute 'name' := 'value'}
  - Generates valid tc6_0200 PLCOpenXML with proper ObjectIds
  - Dynamically handles any FB structure (not hardcoded)

Usage:
  python st_to_plcopenxml.py <input.st> <output.xml>
  
  Or programmatically:
    from st_to_plcopenxml import STConverter
    converter = STConverter()
    converter.convert('MyFB.st', 'MyFB.xml')

Author: Generated for CODESYS conversion workflow
License: MIT
"""

import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def uuid_str() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def escape_xhtml(s: str) -> str:
    """Escape special characters for XML/xhtml bodies."""
    if not s:
        return s
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    return s


class Variable:
    """Represents a variable or constant."""
    def __init__(self, name: str, type_str: str, init_val: Optional[str] = None, is_constant: bool = False):
        self.name = name
        self.type_str = type_str  # e.g., "INT", "ARRAY [1..10] OF REAL"
        self.init_val = init_val
        self.is_constant = is_constant

    def __repr__(self):
        return f"Variable({self.name}: {self.type_str})"


class Method:
    """Represents a function block method."""
    def __init__(self, name: str):
        self.name = name
        self.input_vars: List[Tuple[str, str]] = []  # [(name, type), ...]
        self.output_vars: List[Tuple[str, str]] = []
        self.local_vars: List[Tuple[str, str]] = []
        self.body = ''
        self.object_id = uuid_str()

    def __repr__(self):
        return f"Method({self.name})"


class Property:
    """Represents a function block property."""
    def __init__(self, name: str, type_str: str):
        self.name = name
        self.type_str = type_str
        self.local_vars: List[Tuple[str, str]] = []
        self.body = ''
        self.attribute: Optional[Tuple[str, str]] = None  # (attr_name, attr_value)
        self.object_id = uuid_str()

    def __repr__(self):
        return f"Property({self.name}: {self.type_str})"


class STConverter:
    """Converts Structured Text to PLCOpenXML."""

    def __init__(self):
        self.fb_name = 'FB'
        self.constants: Dict[str, Variable] = {}
        self.variables: Dict[str, Variable] = {}
        self.methods: List[Method] = []
        self.properties: List[Property] = []

    def parse_type(self, type_str: str) -> str:
        """
        Clean and return a type string for XML.
        Handles: INT, REAL, BOOL, ARRAY [...] OF TYPE, etc.
        """
        return type_str.strip()

    def parse_variable_decl(self, name: str, type_str: str, init_val: Optional[str] = None) -> Variable:
        """Parse a variable declaration and return a Variable object."""
        return Variable(name, self.parse_type(type_str), init_val)

    def parse_st(self, text: str) -> None:
        """Parse a .st (Structured Text) file into FB structure."""
        # Extract function block name
        match = re.search(r'FUNCTION_BLOCK\s+(\w+)', text)
        if match:
            self.fb_name = match.group(1)

        # Parse VAR CONSTANT block
        const_match = re.search(r'VAR\s+CONSTANT\s*\n(.*?)\nEND_VAR', text, re.MULTILINE | re.DOTALL)
        if const_match:
            self._parse_var_block(const_match.group(1), is_constant=True)

        # Parse VAR block (before methods) - member variables
        # Look for first VAR...END_VAR that is NOT VAR_INPUT/VAR_OUTPUT/VAR_CONSTANT
        fb_match = re.search(r'FUNCTION_BLOCK\s+\w+(.*?)METHOD\s+PUBLIC', text, re.DOTALL)
        if fb_match:
            fb_section = fb_match.group(1)
            var_match = re.search(r'VAR\s*\n(.*?)\nEND_VAR', fb_section, re.MULTILINE | re.DOTALL)
            if var_match:
                self._parse_var_block(var_match.group(1), is_constant=False)

        # Parse methods
        for method_match in re.finditer(
            r'METHOD\s+PUBLIC\s+(\w+)(.*?)(?=METHOD\s+PUBLIC|PROPERTY\s+PUBLIC|END_FUNCTION_BLOCK)',
            text, re.DOTALL
        ):
            method_name = method_match.group(1)
            method_block = method_match.group(2)
            method = Method(method_name)
            self._parse_method(method, method_block)
            self.methods.append(method)

        # Parse properties
        for prop_match in re.finditer(
            r'PROPERTY\s+PUBLIC\s+(\w+)\s*:\s*(\w+)(.*?)END_PROPERTY',
            text, re.DOTALL
        ):
            prop_name = prop_match.group(1)
            prop_type = prop_match.group(2)
            prop_block = prop_match.group(3)
            prop = Property(prop_name, prop_type)
            self._parse_property(prop, prop_block)
            self.properties.append(prop)

    def _parse_var_block(self, block_text: str, is_constant: bool) -> None:
        """Parse a VAR...END_VAR block and extract variables."""
        target_dict = self.constants if is_constant else self.variables
        
        # Split by variable declarations (look for name : type patterns)
        # Handle multi-line declarations  
        lines = block_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('(*'):
                i += 1
                continue

            # Match: varname : TYPE [:= INIT]
            # TYPE can be simple (INT, REAL) or complex (ARRAY [...] OF TYPE)
            match = re.match(r'(\w+)\s*:\s*(.+?)(?::=\s*(.+))?$', line)
            if match:
                var_name = match.group(1)
                type_str = match.group(2).strip()
                init_val = match.group(3).strip() if match.group(3) else None

                # Handle multi-line ARRAY declarations
                # e.g., ARRAY\n     [1..10]\n     OF REAL
                if 'ARRAY' in type_str.upper():
                    # Collect lines until we close the ARRAY
                    j = i + 1
                    while j < len(lines):
                        type_str += ' ' + lines[j].strip()
                        if 'OF' in lines[j].upper():
                            i = j
                            break
                        j += 1

                var = self.parse_variable_decl(var_name, type_str, init_val)
                target_dict[var_name] = var
            i += 1

    def _parse_method(self, method: Method, block_text: str) -> None:
        """Parse a method block and extract signatures + body."""
        # Extract VAR_INPUT section
        inp_match = re.search(r'VAR_INPUT\s*(.*?)\s*END_VAR', block_text, re.DOTALL)
        if inp_match:
            self._parse_param_section(inp_match.group(1), method.input_vars)

        # Extract VAR_OUTPUT section
        out_match = re.search(r'VAR_OUTPUT\s*(.*?)\s*END_VAR', block_text, re.DOTALL)
        if out_match:
            self._parse_param_section(out_match.group(1), method.output_vars)

        # Extract local VAR section (not VAR_INPUT/OUTPUT)
        local_match = re.search(r'VAR\s*(.*?)\s*END_VAR', block_text, re.DOTALL)
        if local_match:
            self._parse_param_section(local_match.group(1), method.local_vars)

        # Extract body - can be either BEGIN...END_METHOD or code directly followed by END_METHOD
        # First try BEGIN...END_METHOD pattern
        body_match = re.search(r'BEGIN\s*(.*?)\s*END_METHOD', block_text, re.DOTALL)
        if body_match:
            method.body = body_match.group(1).strip()
        else:
            # If no BEGIN, try to extract code after all VAR sections
            # Remove all VAR/VAR_INPUT/VAR_OUTPUT/END_VAR sections, then get what's left before END_METHOD
            cleaned = re.sub(r'(VAR_INPUT|VAR_OUTPUT|VAR)\s*.*?END_VAR\s*', '', block_text, flags=re.DOTALL)
            body_match = re.search(r'(.*?)\s*END_METHOD', cleaned, re.DOTALL)
            if body_match:
                body = body_match.group(1).strip()
                if body:  # Only set if there's actual content
                    method.body = body

    def _parse_property(self, prop: Property, block_text: str) -> None:
        """Parse a property block (PROPERTY GET section)."""
        # Check for attribute pragma
        attr_match = re.search(r"\{attribute\s+['\"](\w+)['\"]\s*:=\s*['\"](\w+)['\"]\}", block_text)
        if attr_match:
            prop.attribute = (attr_match.group(1), attr_match.group(2))

        # Find PROPERTY GET section
        get_match = re.search(r'PROPERTY\s+GET\s*(.*?)(?=END_PROPERTY|$)', block_text, re.DOTALL)
        if get_match:
            get_block = get_match.group(1)

            # Local VAR section within GET
            local_match = re.search(r'VAR\s*(.*?)\s*END_VAR', get_block, re.DOTALL)
            if local_match:
                self._parse_param_section(local_match.group(1), prop.local_vars)

            # Body between BEGIN and END_PROPERTY/GET
            body_match = re.search(r'BEGIN\s*(.*?)(?:END_PROPERTY|$)', get_block, re.DOTALL)
            if body_match:
                prop.body = body_match.group(1).strip()
            else:
                # If no BEGIN, try to extract code after all VAR sections
                cleaned = re.sub(r'VAR\s*.*?END_VAR\s*', '', get_block, flags=re.DOTALL)
                body_match = re.search(r'(.*?)(?:END_PROPERTY|$)', cleaned, re.DOTALL)
                if body_match:
                    body = body_match.group(1).strip()
                    if body:
                        prop.body = body

    def _parse_param_section(self, section_text: str, target_list: List[Tuple[str, str]]) -> None:
        """Parse a parameter/variable section and append (name, type) tuples."""
        lines = section_text.split('\n')
        for line in lines:
            line = line.strip().rstrip(';')
            if not line or line.startswith('(*'):
                continue
            match = re.match(r'(\w+)\s*:\s*(.+)', line)
            if match:
                var_name = match.group(1)
                var_type = match.group(2).strip()
                target_list.append((var_name, var_type))

    def type_to_xml_element(self, type_str: str) -> str:
        """
        Convert a type string to an XML element.
        E.g., "INT" -> "<INT />"
              "ARRAY [1..10] OF REAL" -> "<array><dimension .../><baseType><REAL/></baseType></array>"
        """
        type_str = type_str.strip()

        # Handle ARRAY types
        if 'ARRAY' in type_str.upper():
            array_match = re.match(
                r'ARRAY\s*\[(.*?)\]\s*OF\s*(\w+)',
                type_str, re.IGNORECASE
            )
            if array_match:
                dimension = array_match.group(1).strip()
                base_type = array_match.group(2).strip()
                return f'<array><dimension {dimension} /><baseType><{base_type} /></baseType></array>'
            return '<array><dimension lower="1" upper="100" /><baseType><INT /></baseType></array>'

        # Simple types
        return f'<{type_str} />'

    def generate_xml(self, output_path: Path) -> Path:
        """Generate PLCOpenXML from parsed structure."""
        now = '2026-02-10T00:00:00.0000000'
        project_obj_id = uuid_str()

        # Build member variable XML
        member_vars_const = ''
        member_vars_regular = ''

        for var in self.constants.values():
            type_xml = self.type_to_xml_element(var.type_str)
            init_xml = f'<initialValue><simpleValue value="{var.init_val or "0"}" /></initialValue>' if var.init_val else ''
            member_vars_const += f'''            <variable name="{var.name}">
              <type>
                {type_xml}
              </type>
              {init_xml}
            </variable>
'''

        for var in self.variables.values():
            type_xml = self.type_to_xml_element(var.type_str)
            init_xml = f'<initialValue><simpleValue value="{var.init_val or "0"}" /></initialValue>' if var.init_val else ''
            member_vars_regular += f'''            <variable name="{var.name}">
              <type>
                {type_xml}
              </type>
              {init_xml}
            </variable>
'''

        # Build methods XML
        methods_xml = self._generate_methods_xml()

        # Build properties XML
        props_xml = self._generate_properties_xml()

        # Build project structure
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
            <xhtml xmlns="http://www.w3.org/1999/xhtml" />
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
        output_path.write_text(xml, encoding='utf-8')
        return output_path

    def _generate_methods_xml(self) -> str:
        """Generate XML for all methods."""
        xml = ''
        for m in self.methods:
            input_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>'
                                   for n, t in m.input_vars])
            output_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>'
                                    for n, t in m.output_vars])
            local_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>'
                                   for n, t in m.local_vars])
            body = escape_xhtml(m.body)

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
        """Generate XML for all properties."""
        xml = ''
        for p in self.properties:
            local_vars = ''.join([f'<variable name="{n}"><type>{self.type_to_xml_element(t)}</type></variable>'
                                   for n, t in p.local_vars])
            body = escape_xhtml(p.body)
            local_section = f'<localVars>{local_vars}</localVars>' if p.local_vars else ''

            attr_xml = ''
            if p.attribute:
                attr_xml = f'''                  <addData>
                    <data name="http://www.3s-software.com/plcopenxml/attributes" handleUnknown="implementation">
                      <Attributes>
                        <Attribute Name="{p.attribute[0]}" Value="{p.attribute[1]}" />
                      </Attributes>
                    </data>
                  </addData>
'''

            xml += f'''          <data name="http://www.3s-software.com/plcopenxml/property" handleUnknown="implementation">
            <Property name="{p.name}" ObjectId="{p.object_id}">
              <interface>
                <returnType>
                  {self.type_to_xml_element(p.type_str)}
                </returnType>
              </interface>
              <GetAccessor>
                <interface>
                  {local_section}
{attr_xml}                </interface>
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

    def convert(self, input_st: str, output_xml: str) -> Path:
        """Convert a .st file to PLCOpenXML."""
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


def main():
    """CLI entry point."""
    if len(sys.argv) < 3:
        print('Usage: python st_to_plcopenxml.py <input.st> <output.xml>')
        print('')
        print('Example:')
        print('  python st_to_plcopenxml.py Logger.st Logger.xml')
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        converter = STConverter()
        converter.convert(input_file, output_file)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
