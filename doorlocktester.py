from zigbee import ZBController

door_lock_cluster = ZCLCluster()
door_lock_cluster.id = 0x0101

door_lock_command = ZCLCommand()
door_lock_command.id = 0x00

class DoorLockTester(ZBController):
    def __init__(self):
        super(ZBController, self).__init__()
        self.device_under_test = None

    def wait_for_joined(self):
        self.device_under_test = ZBController.wait_for_join(self)

    def send_lock():
        self._send_cluster_command(door_lock_cluster, door_lock_command)

    def send_zcl_command(self, cluster, command, payload = None):
        if not self.device_under_test:
            print "Please include a device to the network for testing"
            return
        self.send_zcl_command(self.device_under_test, cluster, command, payload)
