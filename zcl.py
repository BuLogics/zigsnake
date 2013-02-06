import xml.etree.ElementTree as xml
import string
import doctest

class ZCLCluster:
    def __init__(self, cluster_xml):
        self.name = cluster_xml.find('name').text
        self.define = cluster_xml.find('define').text
        self.code = int(cluster_xml.find('code').text, 0)
        self.add_commands(cluster_xml)
        self.add_attributes(cluster_xml)

    def add_commands(self, cluster_xml):
        for cmd_xml in cluster_xml.findall('command'):
            setattr(self,
                    _attr_from_name(cmd_xml.get('name')),
                    ZCLCommandPrototype(self.code, cmd_xml))

    def add_attributes(self, cluster_xml):
        for attr_xml in cluster_xml.findall('attribute'):
            setattr(self,
                    _attr_from_name(attr_xml.text),
                    ZCLAttribute(self.code, attr_xml))

class ZCLCommandCall:
    def __init__(self, proto, arglist):
        self.cluster_code = proto.cluster_code
        self.code = proto.code
        self.name = proto.name
        # copy the list to make sure there's no interaction with the given payload
        # note that we're not going as far as copying all the arguments.
        # maybe we should?
        self.args = list(arglist)

class ZCLCommandPrototype:
    '''
    ZCLCommandPrototype represents the call signiture of a ZCL Command.
    It is also callable, and when called will return a ZCLCommandCall object
    with the cluster ID, command ID, a list of the types and values
    '''
    def __init__(self, cluster_code, cmd_xml):
        # a ZCLCommandPrototype needs to know about its cluster ID so that it
        # can generate a proper ZCLCommandCall that can be passed to actually
        # send a message
        self.cluster_code = cluster_code
        self.name = cmd_xml.get('name')
        self.code = int(cmd_xml.get('code'), 0)
        # <pedantic>function parameters are mistakenly called
        # 'args' in the xml </pedantic>
        self.params = [ZCLCommandParam(xml) for xml in cmd_xml.findall('arg')]
    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError("%s() takes exactly %d arguments (%d given)\n" %
                    (_attr_from_name(self.name), len(self.params), len(args)) +
                    "\n".join(["\t\t%s (%s)" % (param.name, param.type) for
                        param in self.params]))
        arglist = [ZCLCommandArg(param.name, param.type, val) for param, val
                in zip(self.params, args)]
        return ZCLCommandCall(self, arglist)

class ZCLCommandParam:
    def __init__(self, param_xml):
        self.name = param_xml.get('name')
        self.type = param_xml.get('type')

class ZCLCommandArg:
    def __init__(self, name, type, value):
        self.name = name
        self.type = type
        self.value = value

class ZCLAttribute:
    def __init__(self, cluster_code, attr_xml=None):
        if attr_xml is None:
            return
        self.name = attr_xml.text
        self.cluster_code = cluster_code
        self.code = int(attr_xml.get('code'), 0)
        self.type = attr_xml.get('type')
        self.type_code = zcl_attribute_type_codes[self.type]
        if self.type in ['INT16U', 'INT16S', 'ENUM16', 'BITMAP16']:
            self.size = 2
        elif self.type in ['INT32U', 'INT32S', 'ENUM32', 'UTC_TIME', 'BITMAP32', 'IEEE_ADDRESS']:
            self.size = 4
        elif self.type in ['CHAR_STRING', 'OCTET_STRING']:
            self.size = None
        else:
            self.size = 1

class ZCLEnum:
    def __init__(self, enum_xml):
        self.name = enum_xml.get('name')
        for item_xml in enum_xml.findall('item'):
            setattr(self, _attr_from_name(item_xml.get('name')),
                int(item_xml.get('value'),0))

class ZCL:
    def __init__(self, xml_files = None):
        clusters = []
        if not xml_files:
            return
        for xml_file in xml_files:
            tree = xml.parse(xml_file)
            root = tree.getroot()
            for cluster_xml in root.iter('cluster'):
                setattr(self,
                        _attr_from_name(cluster_xml.find('name').text),
                        ZCLCluster(cluster_xml))
            for extension_xml in root.iter('clusterExtension'):
                for cluster in (getattr(self, match) for match in dir(self)):
                    if cluster.__class__ == ZCLCluster \
                            and cluster.code == int(extension_xml.get('code'), 0):
                        cluster.add_commands(extension_xml)
                        cluster.add_attributes(extension_xml)
            for enum_xml in root.iter('enum'):
                setattr(self,
                        _attr_from_name(enum_xml.get('name')),
                        ZCLEnum(enum_xml))

def _attr_from_name(name):
    '''
    This assumes that the name is either in CamelCase or
    words separated by spaces, and converts to all lowercase
    with words separated by underscores. It also removes
    any punctuation from the space-separated names.

    >>> _attr_from_name('This is a name with spaces')
    'this_is_a_name_with_spaces'
    >>> _attr_from_name('this is a name with spaces')
    'this_is_a_name_with_spaces'
    >>> _attr_from_name('ThisIsACamelCaseName')
    'this_is_a_camel_case_name'
    >>> _attr_from_name('thisIsAnotherCamelCaseName')
    'this_is_another_camel_case_name'
    >>> _attr_from_name('this-has.some Punctuation')
    'thishassome_punctuation'
    '''
    if ' ' in name:
        return name.translate(
                string.maketrans(' ', '_'), string.punctuation).lower()
    #no spaces, so look for uppercase letters and prepend an underscore
    attr_name = ''
    for i, letter in enumerate(name):
        if letter.isupper() and i != 0:
            attr_name += '_'
        attr_name += letter.lower()
    return attr_name

# as far as I can tell this isn't stored in any of the XML
# files, so we just hard-code it here
zcl_attribute_type_codes = {
    'NO_DATA'           : 0x00,
    'DATA8'             : 0x08,
    'DATA16'            : 0x09,
    'DATA24'            : 0x0A,
    'DATA32'            : 0x0B,
    'DATA40'            : 0x0C,
    'DATA48'            : 0x0D,
    'DATA56'            : 0x0E,
    'DATA64'            : 0x0F,
    'BOOLEAN'           : 0x10,
    'BITMAP8'           : 0x18,
    'BITMAP16'          : 0x19,
    'BITMAP24'          : 0x1A,
    'BITMAP32'          : 0x1B,
    'BITMAP40'          : 0x1C,
    'BITMAP48'          : 0x1D,
    'BITMAP56'          : 0x1E,
    'BITMAP64'          : 0x1F,
    'INT8U'             : 0x20,
    'INT16U'            : 0x21,
    'INT24U'            : 0x22,
    'INT32U'            : 0x23,
    'INT40U'            : 0x24,
    'INT48U'            : 0x25,
    'INT56U'            : 0x26,
    'INT64U'            : 0x27,
    'INT8S'             : 0x28,
    'INT16S'            : 0x29,
    'INT24S'            : 0x2A,
    'INT32S'            : 0x2B,
    'INT40S'            : 0x2C,
    'INT48S'            : 0x2D,
    'INT56S'            : 0x2E,
    'INT64S'            : 0x2F,
    'ENUM8'             : 0x30,
    'ENUM16'            : 0x31,
    'FLOAT_SEMI'        : 0x38,
    'FLOAT_SINGLE'      : 0x39,
    'FLOAT_DOUBLE'      : 0x3A,
    'OCTET_STRING'      : 0x41,
    'CHAR_STRING'       : 0x42,
    'LONG_OCTET_STRING' : 0x43,
    'LONG_CHAR_STRING'  : 0x44,
    'ARRAY'             : 0x48,
    'STRUCT'            : 0x4C,
    'SET'               : 0x50,
    'BAG'               : 0x51,
    'TIME_OF_DAY'       : 0xE0,
    'DATE'              : 0xE1,
    'UTC_TIME'          : 0xE2,
    'CLUSTER_ID'        : 0xE8,
    'ATTRIBUTE_ID'      : 0xE9,
    'BACNET_OID'        : 0xEA,
    'IEEE_ADDRESS'      : 0xF0,
    'SECURITY_KEY'      : 0xF1,
    'UNKNOWN'           : 0xFF
}

# create inverse dictionary for looking up attribute types from type codes
zcl_attribute_types = dict([(v,k) for k,v in zcl_attribute_type_codes.items()])

def get_type_string(type_code):
    return zcl_attribute_types[type_code]

if __name__ == "__main__":
    doctest.testmod()
