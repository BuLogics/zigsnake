from telnetlib import Telnet

class ZBCluster:
    pass

class ZBCommand:
    pass

class ZBController(Telnet):
    def __init__(self):
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
        self.write('raw 0x%04X {01 %02X %02X %02X %s}\n' %
                (cluster.id, sequence, command.id, len(payload),
                " ".join(["%02X" % x for x in payload])))
        self.write('send %04X 1 1' % destination)
        self.sequence = self.sequence + 1 % 0x100

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass