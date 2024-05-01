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
from mininet.node import Controller, OVSSwitch

defaultIP = '192.168.1.1/24'  # IP address for r0-eth1

class LinuxRouter( Node ):
    "A Node with IP forwarding enabled."

    def config( self, **params ):
        super( LinuxRouter, self).config( **params )
        # Enable forwarding on the router
        self.cmd( 'sysctl net.ipv4.ip_forward=1' )

    def terminate( self ):
        self.cmd( 'sysctl net.ipv4.ip_forward=0' )
        super( LinuxRouter, self ).terminate()

def multiControllerNet():
    "Create a network from semi-scratch with multiple controllers."

    net = Mininet( controller=Controller, switch=OVSSwitch,
                   waitConnected=True )

    info( "*** Creating (reference) controllers\n" )
    c1 = net.addController('c1', controller=RemoteController, ip='127.0.0.1', protocol='tcp', port=6633)
    c2 = net.addController('c2')


    info( "*** Creating router\n" )
    router = net.addHost( 'r0', cls=LinuxRouter, ip=defaultIP )

    info( "*** Creating switches\n" )
    s1 = net.addSwitch( 's1' )
    s2 = net.addSwitch( 's2' )


    info( "*** Creating links\n" )
    net.addLink( s1, router, intfName2='r0-eth1',
                    params2={ 'ip' : defaultIP } )  # for clarity
    net.addLink( s2, router, intfName2='r0-eth2',
                    params2={ 'ip' : '172.16.0.1/12' } )

    info( "*** Creating hosts\n" )
    h1 = net.addHost( 'h1', ip='192.168.1.100/24',
                           defaultRoute='via 192.168.1.1' )
    h2 = net.addHost( 'h2', ip='192.168.1.101/24',
                        defaultRoute='via 192.168.1.1' )

    h8 = net.addHost( 'h8', ip='172.16.0.101/12',
                        defaultRoute='via 172.16.0.1' )
    h9 = net.addHost( 'h9', ip='172.16.0.100/12',
                        defaultRoute='via 172.16.0.1' )

    # Wire the switches with hosts
    for h, s in [ (h1, s1), (h2, s1), (h8, s2), (h9, s2)]:
        net.addLink( h, s )
    
    info( "*** Starting network\n" )
    net.build()
    c1.start()
    c2.start()
    s1.start( [ c1 ] )
    s2.start( [ c2 ] )

    info( "*** Running CLI\n" )
    CLI( net )

    info( "*** Stopping network\n" )
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )  # for CLI output
    multiControllerNet()