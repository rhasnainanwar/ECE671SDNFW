# Copyright 2011-2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An L2 learning switch.

It is derived from one written live for an SDN crash course.
It is somwhat similar to NOX's pyswitch in that it installs
exact-match rules for each flow.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.util import str_to_bool
from pox.lib.addresses import IPAddr
import time

# constants
DROP_DURATION = 10
IDLE_TIMEOUT = 10
HARD_TIMEOUT = 30

log = core.getLogger()

# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0

class LearningSwitch (object):
  """
  The learning switch "brain" associated with a single OpenFlow switch.

  When we see a packet, we'd like to output it on a port which will
  eventually lead to the destination.  To accomplish this, we build a
  table that maps addresses to ports.

  We populate the table by observing traffic.  When we see a packet
  from some source coming from some port, we know that source is out
  that port.

  When we want to forward traffic, we look up the desintation in our
  table.  If we don't know the port, we simply send the message out
  all ports except the one it came in on.  (In the presence of loops,
  this is bad!).
  """

  def __init__ (self, connection, transparent):
    # Switch we'll be adding L2 learning switch capabilities to
    self.connection = connection
    self.transparent = transparent

    # Our table
    self.macToPort = {}
    self.connections = {}

    # Define firewall rule parameters
    self.inside_network = IPAddr("192.168.1.0")  # Inside network IP address
    self.inside_subnet = 24  # Inside network subnet mask

    # We want to hear PacketIn messages, so we listen
    # to the connection
    connection.addListeners(self)

    # We just use this to know when to log a helpful message
    self.hold_down_expired = _flood_delay == 0

  def print_connections(self):
    # Print active connections
    out = "\nActive connections:\n"
    for conn_str in self.connections:
      out += "%s\n" % conn_str
    log.info(out)

  def add_connection(self, conn_str):
    # Add connection to the dictionary
    self.connections[conn_str] = time.time()
    self.print_connections()
  
  def remove_connection(self, conn_str):
    # Remove connection from the dictionary
    if conn_str in self.connections:
      del self.connections[conn_str]
    self.print_connections()

  def is_established(self, conn_str):
    # Check if the packet is part of an established connection
    # Check if the outbound connection exists
    return conn_str in self.connections
  

  def _handle_PacketIn(self, event):
    """
    Handle packet in messages from the switch to implement above algorithm.
    """

    packet = event.parsed
    # Extract IP layer from the packet
    ip_packet = packet.find('ipv4')

    def flood (message = None):
      """ Floods the packet """
      msg = of.ofp_packet_out()
      if time.time() - self.connection.connect_time >= _flood_delay:
        # Only flood if we've been connected for a little while...

        if self.hold_down_expired is False:
          # Oh yes it is!
          self.hold_down_expired = True
          log.info("%s: Flood hold-down expired -- flooding",
              dpid_to_str(event.dpid))

        if message is not None: log.debug(message)
        #log.debug("%i: flood %s -> %s", event.dpid,packet.src,packet.dst)
        # OFPP_FLOOD is optional; on some switches you may need to change
        # this to OFPP_ALL.
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
      else:
        pass
        #log.info("Holding down flood for %s", dpid_to_str(event.dpid))
      msg.data = event.ofp
      msg.in_port = event.port
      self.connection.send(msg)

    def drop (duration = None):
      """
      Drops this packet and optionally installs a flow to continue
      dropping similar ones for a while
      """
      if duration is not None:
        if not isinstance(duration, tuple):
          duration = (duration,duration)
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = duration[0]
        msg.hard_timeout = duration[1]
        msg.buffer_id = event.ofp.buffer_id
        self.connection.send(msg)
      elif event.ofp.buffer_id is not None:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)

    self.macToPort[packet.src] = event.port # 1

    if not self.transparent: # 2
      if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
        drop() # 2a
        return


    """
    The switch FIREWALL logic goes here.
    """
    if ip_packet: # If it's an IP packet
      src_ip = ip_packet.srcip
      dst_ip = ip_packet.dstip

      # log.info("Packet from %s to %s" % (src_ip, dst_ip))
      # log.info("Port: %s" % event.port)

      tcp_packet = packet.find('tcp')
      if tcp_packet:
        src_port = tcp_packet.srcport
        dst_port = tcp_packet.dstport

      conn_str = "" # inIP:inPort-outIP:outPort

      # Check if packet is from inside network going outside
      if src_ip.inNetwork(self.inside_network, self.inside_subnet) and dst_ip.inNetwork(self.inside_network, self.inside_subnet):
        log.info("Firewall: Local network traffic")
      elif src_ip.inNetwork(self.inside_network, self.inside_subnet) and not dst_ip.inNetwork(self.inside_network, self.inside_subnet):
        if tcp_packet:
          log.info("Firewall: Packet IN->OUT: %s:%s -> %s:%s" % (src_ip, src_port, dst_ip, dst_port))
          conn_str = "%s:%s-%s:%s" % (src_ip, src_port, dst_ip, dst_port)

          if tcp_packet.SYN and not tcp_packet.ACK: # new connection
            log.info("Firewall: SYN packet, adding to active connections.")
            self.add_connection(conn_str)
          elif tcp_packet.RST or tcp_packet.FIN: # connection reset or closed
            log.info("Firewall: RST or FIN packet, removing from active connections.")
            self.remove_connection(conn_str)
      else:
        if tcp_packet:
          log.info("Firewall: Packet OUT->IN: %s:%s -> %s:%s" % (src_ip, src_port, dst_ip, dst_port))
          conn_str = "%s:%s-%s:%s" % (dst_ip, dst_port, src_ip, src_port)
          
          if tcp_packet.RST or tcp_packet.FIN: # connection reset or closed
            log.info("Firewall: RST or FIN packet, removing from active connections.")
            self.remove_connection(conn_str)
            # Not part of an established connection
          if not self.is_established(conn_str):
            log.info("Firewall:UNAUTHORIZED: Dropping packet from %s:%s" % (src_ip, src_port))
            drop(DROP_DURATION)
          # otherwise, allow the packet and use learning logic 
        else:
          log.info("Firewall: Dropping non-TCP packet.")
          self.remove_connection(conn_str)

    """
    The LEARNING switch logic goes here.
    """
    # 3) Is destination multicast?
    if packet.dst.is_multicast:
      # 3a) Flood the packet
      flood(f"Dst: [{(packet.dst,)}] is multicast -- flooding.")
    else: # 4) Port for destination address in our address/port table?
      if packet.dst not in self.macToPort: # No:
        # 4a) Flood the packet
        flood(f"Dst: [{(packet.dst,)}], port unknown -- flooding.")
      else: # 5
        port = self.macToPort[packet.dst]
        # 5a) Is output port the same as input port?
        if event.port == port:
          log.warning(f"Same port for packet from Src: [{packet.src}] -> Dst: [{packet.dst}] on Port {dpid_to_str(event.dpid)}.{port} -- dropping for {DROP_DURATION}s.")
          # 5a) Drop packet and similar ones for a while
          drop(DROP_DURATION) #idling
          return
        
        # 6) Install flow table entry in the switch so that this flow goes out the appopriate port
        log.debug(f"Installing flow for Src: [{packet.src}.{event.port}] -> Dst: [{packet.dst}.{port}]")
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet, event.port)
        msg.idle_timeout = IDLE_TIMEOUT
        msg.hard_timeout = HARD_TIMEOUT
        msg.actions.append(of.ofp_action_output(port = port))
        msg.data = event.ofp
        # 6a) Send the packet out appropriate port
        self.connection.send(msg)


class l2_learning (object):
  """
  Waits for OpenFlow switches to connect and makes them learning switches.
  """
  def __init__ (self, transparent):
    core.openflow.addListeners(self)
    self.transparent = transparent

  def _handle_ConnectionUp (self, event):
    log.debug("Connection %s" % (event.connection,))
    LearningSwitch(event.connection, self.transparent)


def launch (transparent=False, hold_down=_flood_delay):
  """
  Starts an L2 learning switch.
  """
  try:
    global _flood_delay
    _flood_delay = int(str(hold_down), 10)
    assert _flood_delay >= 0
  except:
    raise RuntimeError("Expected hold-down to be a number")

  core.registerNew(l2_learning, str_to_bool(transparent))

