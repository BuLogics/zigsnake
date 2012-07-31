from telnetlib import Telnet
import xml.etree.ElementTree as xml

class ZCLCluster:
    def __init__(self, xml_node):
        for attr in ['name', 'define', 'code']:
            setattr(self, attr, xml_node.find(attr).text)

class ZCLCommand:
    pass

class ZCLAttribute:
    pass

class ZBController(Telnet):
    def __init__(self, xml_files = None):
        Telnet.__init__(self)
        self.sequence = 0
        if not xml_files:
            return
        clusters = []
        for xml_file in xml_files:
            tree = xml.parse(xml_file)
            root = tree.getroot()
            for cluster_xml in root.iter('cluster'):
                clusters.append(ZCLCluster(cluster_xml))

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
        _, match, _ = self.expect(['RX len [0-9]+, ep [0-9A-Z]+, clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)]' % (cluster,command)], timeout=2)
        if match is None:
            raise TimeoutError()
        return [int(x, 16) for x in match.group(1).split()]

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass
