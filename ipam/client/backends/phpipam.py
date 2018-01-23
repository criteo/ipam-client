#!/usr/bin/env python

import mysql.connector
import sqlite3
from ipam.client.abstractipam import AbstractIPAM
from netaddr import IPAddress, IPNetwork


class PHPIPAM(AbstractIPAM):

    def __init__(self, params):
        dbtype = 'mysql'
        section_name = 'Production'
        if 'section_name' in params:
            section_name = params['section_name']
        if 'dbtype' in params:
            dbtype = params['dbtype']
        if dbtype == 'sqlite':
            self.db = sqlite3.connect(params['database_uri'])
            self.dbtype = 'sqlite'
        else:  # defaults to mysql
            self.db = mysql.connector.connect(
                host=params['database_host'],
                user=params['username'],
                password=params['password'],
                database=params['database_name']
            )
            self.dbtype = 'mysql'
        self.cur = self.db.cursor()
        self.set_section_id_by_name(section_name)

    def set_section_id(self, section_id):
        self.section_id = section_id

    def set_section_id_by_name(self, section_name):
        self.cur.execute(
            "SELECT id FROM sections WHERE name = '%s'" % (section_name)
        )
        row = self.cur.fetchone()
        if row is None:
            raise ValueError(
                "Can't get section id matching %s" % (section_name)
            )
        self.set_section_id(row[0])

    def get_section_id(self):
        return self.section_id

    def find_subnet_id(self, subnet):
        network = int(subnet.network)
        self.cur.execute("SELECT id FROM subnets WHERE subnet='%d' \
                         AND mask='%d'"
                         % (network, subnet.prefixlen))
        row = self.cur.fetchone()
        if row is not None:
            return int(row[0])
        return None

    def add_ip(self, ipaddress, dnsname, description):
        """ Adds an IP address in IPAM. ipaddress must be an
        instance of IPNetwork. Returns True """
        subnetid = self.find_subnet_id(ipaddress)
        if subnetid is None:
            raise ValueError("Unable to get subnet id from database \
                             for subnet %s/%s"
                             % (ipaddress.network, ipaddress.prefixlen))
        self.cur.execute("SELECT ip_addr FROM ipaddresses \
                         WHERE ip_addr='%d' AND subnetId=%d"
                         % (int(ipaddress.ip), subnetid))
        row = self.cur.fetchone()
        if row is not None:
            raise ValueError("IP address %s already registered"
                             % (ipaddress.ip))
        self.cur.execute("INSERT INTO ipaddresses \
                         (subnetId, ip_addr, description, dns_name) \
                         VALUES (%d, '%d', '%s', '%s')"
                         % (subnetid, int(ipaddress.ip),
                            description, dnsname))
        self.db.commit()
        return True

    def add_next_ip(self, subnet, dnsname, description):
        """ Finds next free ip in subnet, and adds it in IPAM.
        Returns IP address as IPNetwork """
        ipaddress = self.get_next_free_ip(subnet)
        if not self.add_ip(ipaddress, dnsname, description):
            raise ValueError("Unable to add IP address %s" % ipaddress)
        return ipaddress

    def get_next_free_ip(self, subnet):
        """ Finds next free ip in subnet. Returns IP address as IPNetwork """
        # Find PHPIPAM subnet id
        subnetid = self.find_subnet_id(subnet)
        if subnetid is None:
            raise ValueError("Unable to get subnet id from database \
                             for subnet %s/%s"
                             % (subnet.network, subnet.prefixlen))
        # Create hosts list in subnet
        subnetips = subnet.iter_hosts()
        # Get allocated ip addresses from database
        usedips = self.get_allocated_ips_by_subnet_id(subnetid)

        # Dirty hack, as netaddr has no support for RFC 6164 /127 subnets
        # https://github.com/drkjam/netaddr/pull/168
        if subnet.prefixlen == 127:
            subnetips = list(subnetips)
            subnetips.append(subnet.network)

        subnetips = set(subnetips)
        usedips = set(usedips)
        # Compute the difference between sets, aka available ip addresses set
        availableips = subnetips.difference(usedips)
        # Make a list from the set so we can sort it
        availableips = list(availableips)
        availableips.sort()
        if len(availableips) <= 0:
            raise ValueError("Subnet %s/%s is full"
                             % (subnet.network, subnet.prefixlen))
        # Return first available ip address in the list
        return IPNetwork("%s/%d" % (availableips[0], subnet.prefixlen))

    def get_allocated_ips_by_subnet_id(self, subnetid):
        self.cur.execute("SELECT ip_addr FROM ipaddresses \
                         WHERE subnetId=%d ORDER BY ip_addr ASC"
                         % (subnetid))
        iplist = [IPAddress(int(ip[0])) for ip in self.cur]
        return iplist

    def get_hostname_by_ip(self, ip):
        ip = int(ip)
        self.cur.execute("SELECT dns_name FROM ipaddresses \
                         WHERE ip_addr='%d'"
                         % ip)
        row = self.cur.fetchone()
        if row is not None:
            return row[0]
        return None

    def get_description_by_ip(self, ip):
        ip = int(ip)
        self.cur.execute("SELECT description FROM ipaddresses \
                         WHERE ip_addr='%d'"
                         % ip)
        row = self.cur.fetchone()
        if row is not None:
            return row[0]
        return None

    def get_ipnetwork_list_by_desc(self, description):
        self.cur.execute("SELECT ip.ip_addr,ip.description,ip.dns_name,\
                              s.mask,s.description,v.number\
                          FROM ipaddresses ip\
                          LEFT JOIN subnets s ON\
                              ip.subnetId = s.id\
                          LEFT JOIN vlans v ON\
                              s.vlanId = v.vlanId\
                          WHERE ip.description LIKE '%s'\
                              AND ip.state = 1"
                         % (description))
        iplist = list()
        for row in self.cur:
            item = {}
            ip_address = IPAddress(int(row[0]))
            item['ip'] = IPNetwork(str(ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            item['vlan_id'] = row[5]
            iplist.append(item)
        return iplist

    def get_ipnetwork_by_desc(self, description):
        iplist = self.get_ipnetwork_list_by_desc(description)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_ipnetwork_list_by_subnet_name(self, subnet_name):
        self.cur.execute("SELECT ip.ip_addr,ip.description,ip.dns_name,\
                              s.mask,s.description\
                          FROM ipaddresses ip\
                          LEFT JOIN subnets s ON\
                              ip.subnetId = s.id\
                          WHERE s.description LIKE '%s'\
                              AND ip.state = 1"
                         % (subnet_name))
        iplist = list()
        for row in self.cur:
            item = {}
            ip_address = IPAddress(int(row[0]))
            item['ip'] = IPNetwork(str(ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            iplist.append(item)
        return iplist

    def get_ipnetwork_by_subnet_name(self, subnet_name):
        iplist = self.get_ipnetwork_list_by_desc(subnet_name)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_ip_list_by_desc(self, description):
        self.cur.execute("SELECT ip_addr,description,dns_name \
                         FROM ipaddresses \
                         WHERE description LIKE '%s'\
                              AND state = 1"
                         % (description))
        iplist = list()
        for row in self.cur:
            item = {}
            item['ip'] = IPAddress(int(row[0]))
            item['description'] = row[1]
            item['dnsname'] = row[2]
            iplist.append(item)
        return iplist

    def get_ip_by_desc(self, description):
        iplist = self.get_ip_list_by_desc(description)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_subnet_list_by_desc(self, description):
        self.cur.execute("SELECT subnet,mask,description FROM subnets \
                         WHERE description LIKE '%s'"
                         % description)
        netlist = list()
        for row in self.cur:
            item = {}
            subnet = str(IPAddress(int(row[0])))
            item['subnet'] = IPNetwork("%s/%s" % (subnet, row[1]))
            item['description'] = row[2]
            netlist.append(item)
        return netlist

    def get_subnet_by_desc(self, description):
        subnetlist = self.get_subnet_list_by_desc(description)
        if subnetlist == []:
            return None
        else:
            return subnetlist[0]

    def get_subnet_by_id(self, subnetid):
        self.cur.execute("SELECT subnet,mask,description FROM subnets \
                         WHERE id=%d"
                         % subnetid)
        row = self.cur.fetchone()
        if row is not None:
            item = {}
            subnet = str(IPAddress(int(row[0])))
            item['subnet'] = IPNetwork("%s/%s" % (subnet, row[1]))
            item['description'] = row[2]
            return item
        return None

    def get_num_ips_by_desc(self, description):
        self.cur.execute("SELECT COUNT(ip_addr) FROM ipaddresses \
                         WHERE description LIKE '%s'\
                              AND state = '1'"
                         % (description))
        row = self.cur.fetchone()
        if row is not None:
            return int(row[0])
        return None

    def get_num_subnets_by_desc(self, description):
        self.cur.execute("SELECT COUNT(subnet) FROM subnets \
                         WHERE description LIKE '%s'"
                         % description)
        row = self.cur.fetchone()
        if row is not None:
            return int(row[0])
        return None

    def __del__(self):
        self.db.close()
