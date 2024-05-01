#!/usr/bin/python

"""
Network with Linux IP router

Converts a Node into a router using IP forwarding
already built into Linux.

Topology creates a router and three IP subnets:

    - 192.168.1.0/24 (r0-eth1, IP: 192.168.1.1)
    - 172.16.0.0/12 (r0-eth2, IP: 172.16.0.1)

Each subnet consists of a single host connected to
a single switch:

    r0-eth1 - self.s1-eth1 - c1-eth0 (IP: 192.168.1.100)
    r0-eth2 - self.s2-eth1 - h1-eth0 (IP: 172.16.0.100)

This relies on default routing entries that are
automatically created for each router interface, as well
as 'defaultRoute' parameters for the host interfaces.

Additional routes may be added to the router or hosts by
executing 'ip route' or 'route' commands on the router or hosts.
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Node
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import RemoteController

class LinuxRouter( Node ):
    "A Node with IP forwarding enabled."

    def config( self, **params ):
        super( LinuxRouter, self).config( **params )
        # Enable forwarding on the router
        self.cmd( 'sysctl net.ipv4.ip_forward=1' )

    def terminate( self ):
        self.cmd( 'sysctl net.ipv4.ip_forward=0' )
        super( LinuxRouter, self ).terminate()


class NetworkTopo( Topo ):
    "A LinuxRouter connecting three IP subnets"

    def build( self, **_opts ):

        defaultIP = '192.168.1.1/24'  # IP address for r0-eth1
        
        # Add router
        router = self.addNode( 'r0', cls=LinuxRouter, ip=defaultIP )

        # Add switches
        self.s1 = self.addSwitch('s1')
        self.s2 = self.addSwitch('s2')

        # Add links
        self.addLink( self.s1, router, intfName2='r0-eth1',
                      params2={ 'ip' : defaultIP } )  # for clarity
        self.addLink( self.s2, router, intfName2='r0-eth2',
                      params2={ 'ip' : '172.16.0.1/12' } )

        # Add hosts
        c1 = self.addHost( 'c1', ip='192.168.1.100/24',
                           defaultRoute='via 192.168.1.1' )
        c2 = self.addHost( 'c2', ip='192.168.1.101/24',
                           defaultRoute='via 192.168.1.1' )

        h1 = self.addHost( 'h1', ip='172.16.0.100/12',
                           defaultRoute='via 172.16.0.1' )

        # Wire the switches with hosts
        for h, s in [ (c1, self.s1), (c2, self.s1), (h1, self.s2)]:
            self.addLink( h, s )

def run():
    "Test linux router"
    topo = NetworkTopo()
    net = Mininet( topo=topo)  # controller is used by self.s1-s3

    # Connect to remote controller
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', protocol='tcp', port=6633)
    net.addController('c1')
    net.start()

    info( '*** Routing Table on Router:\n' )
    print(net[ 'r0' ].cmd( 'route' ))
    CLI( net )
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    run()