from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import IPAddr

# Reference to the POX core object
log = core.getLogger()

# Define the Controller class
class MyFirewallController(object):
    def __init__(self):
        # Register for OpenFlow messages
        core.openflow.addListeners(self)

        # Define firewall rule parameters
        self.inside_network = IPAddr("192.168.1.100")  # Inside network IP address
        self.inside_subnet = 24  # Inside network subnet mask
        self.outside_network = IPAddr("172.16.0.100")  # Outside network IP address
        self.outside_subnet = 12  # Outside network subnet mask
        self.connections = {}  # Dictionary to store established connections

    def _handle_PacketIn(self, event):
        packet = event.parsed
        # Extract IP layer from the packet
        ip_packet = packet.find('ipv4')
        if ip_packet is None:
            # Not an IP packet, drop it
            self.drop_packet(event)
            return
        
        src_ip = ip_packet.srcip
        dst_ip = ip_packet.dstip

        print("Packet from %s to %s" % (src_ip, dst_ip))
        print("Port: %s" % event.port)


        # Check if packet is from inside network going outside
        if src_ip.inNetwork(self.inside_network, self.inside_subnet) and dst_ip.inNetwork(self.outside_network, self.outside_subnet):
            # Check if packet is part of an established connection
            if self.is_established(src_ip, dst_ip):
                # Allow the packet and install flow entry
                self.allow_packet(event)
            else:
                # Drop the packet if it's not part of an established connection
                print("Dropping packet")
                self.drop_packet(event)
        else:
            # Allow other packets (from outside to inside)
            self.allow_packet(event)

    def is_established(self, src_ip, dst_ip):
        # Check if the packet is part of an established connection
        # Check if the outbound connection exists
        return (dst_ip, src_ip) in self.connections

    def drop_packet(self, event):
        # Drop the packet
        msg = of.ofp_packet_out()
        msg.data = event.ofp
        event.connection.send(msg)

    def allow_packet(self, event):
        # Allow the packet and install flow entry
        match = of.ofp_match.from_packet(event.parsed)
        actions = of.ofp_action_output(port=of.OFPP_FLOOD)
        msg = of.ofp_flow_mod(match=match, actions=actions)
        event.connection.send(msg)

def launch():
    # Initialize the controller
    core.registerNew(MyFirewallController)
