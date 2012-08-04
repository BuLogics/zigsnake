from telnetlib import Telnet
import xml.etree.ElementTree as xml

class ZCLCluster:
    def __init__(self, cluster_xml):
        self.name = cluster_xml.find('name').text
        self.define = cluster_xml.find('define').text
        self.code = int(cluster_xml.find('define').text, 0)
        for attr_xml in cluster_xml.find('attribute'):
            setattr(self,
                    _attr_from_name(attr_xml.text),
                    ZCLAttribute(attr_xml))
        for cmd_xml in cluster_xml.find('command'):
            def cmd_func(self, *args):
                # need to figure out what's useful for this cmd to return
                pass
            setattr(self,
                    _attr_from_name(cmd_xml.get('name')),
                    cmd_func)

class ZCLCommand:
    def __init__(self, cmd_xml):
        self.name = cmd_xml.get('name')
        self.code = int(cmd_xml.get('code'), 0)
        self.args = [ZCLCommandArg(arg_xml) for arg_xml in cmd_xml.find('arg')]
    def __call__(self, *args):
        pass

class ZCLCommandArg:
    def __init__(self, arg_xml):
        self.name = arg_xml.get('name')
        self.type = arg_xml.get('type')

class ZCLAttribute:
    def __init__(self, attr_xml):
        self.name = attr_xml.text
        self.code = int(attr_xml.get('code'), 0)
        self.type = attr_xml.get('type')

class ZCLCommandGenerator():
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
    @staticmethod
    def _attr_from_name(name):
        '''This assumes that the name is either in CamelCase or
        words separated by spaces, and converts to all lowercase
        with words separated by underscores.'''
        if ' ' in name:
            return name.replace(' ', '_').lower()
        #no spaces, so look for uppercase letters and prepend an underscore
        attr_name = ''
        for i, letter in enumerate(name):
            if letter.isupper() and i != 0:
                attr_name += '_'
            attr_name += letter.lower()
        return attr_name

class ZBController(Telnet):
    def __init__(self, xml_files = None):
        Telnet.__init__(self)
        self.sequence = 0

    def open(self, hostname):
        Telnet.open(self, hostname, 4900)

    def _network_command(self, command, args, status_prefix):
        self.write('network %s %s\n' % (command, args))
        _, match, _ = self.expect(['%s (0x[0-9A-F]{2})' % status_prefix], timeout=2)
        if match is None:
            raise TimeoutError()
        return int(match.group(1), 0)

    def form_network(self):
        status = self._network_command('form', '19 0 0xbabe', 'form')
        if status == 0x70:
            print "Already in Network"
        elif status == 0x00:
            print "Successfully formed network"
        else:
            raise UnhandledStatusError()

    def leave_network(self):
        status = self._network_command('leave', '', 'leave')
        if status == 0x70:
            print "Already Out of Network"
        elif status == 0x00:
            out = self.read_until('EMBER_NETWORK_DOWN', timeout=2)
            if out.endswith('EMBER_NETWORK_DOWN'):
                print "Successfully left network"
            else:
                raise TimeoutError()
        else:
            raise UnhandledStatusError()

    def enable_permit_join(self):
        status = self._network_command('pjoin', '0xff', 'pJoin for 255 sec:')
        if status == 0x00:
            print "Pjoin Enabled"
        else:
            print "Error enabling pjoin: 0x%x" % status

    def disable_permit_join(self):
        status = self._network_command('pjoin', '0x00', 'pJoin for 0 sec:')
        if status == 0x00:
            print "Pjoin Disabled"
        else:
            print "Error disabling pjoin: 0x%x" % status

    def wait_for_join(self):
        _, match, _ = self.expect(['Device Announce: (0x[0-9A-F]{4})'])
        if match is None:
            raise TimeoutError()
        print 'Device %s joined' % match.group(1)
        return int(match.group(1), 0)

    def send_zcl_command(self, destination, cluster, command, payload = None):
        if not payload:
            payload = []
        self.write('raw 0x%04X {01 %02X %02X %s}\n' %
                (cluster, self.sequence, command,
                " ".join(["%02X" % x for x in payload])))
        self.write('send 0x%04X 1 1\n' % destination)
        self.sequence = self.sequence + 1 % 0x100

    #T000931A2:RX len 15, ep 01, clus 0x0101 (Door Lock) FC 09 seq 4E cmd 06 payload[06 00 01 00 06 06 36 37 38 39 30 30 ]
    def wait_for_command(self, cluster, command):
        "Returns the payload as a list of ints"
        _, match, _ = self.expect(['RX len [0-9]+, ep [0-9A-Z]+, clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)]' % (cluster,command)], timeout=20)
        if match is None:
            raise TimeoutError()
        return [int(x, 16) for x in match.group(1).split()]

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass
