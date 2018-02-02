from __future__ import unicode_literals
import mysql.connector
import sqlite3
from ipam.client.abstractipam import AbstractIPAM
from ipaddress import ip_address, ip_interface, ip_network

DEFAULT_IPAM_DB_TYPE = 'mysql'

DEFAULT_SUBNET_OPTIONS = {
    # Default permissions: read-only for guests and operators
    'permissions': '{"2":"1","3":"1"}',
    'vlan_id': 0,
    'vrf_id': 0,
}


class PHPIPAM(AbstractIPAM):

    def __init__(self, params):
        dbtype = DEFAULT_IPAM_DB_TYPE
        subnet_options = DEFAULT_SUBNET_OPTIONS.copy()
        for (option, value) in DEFAULT_SUBNET_OPTIONS.items():
            param_name = 'subnet_{}'.format(option)
            if params.get(param_name):
                value = params[param_name]
            subnet_options[option] = value
        self.subnet_options = subnet_options
        section_name = 'Production'
        if 'section_name' in params:
            section_name = params['section_name']
        if 'dbtype' in params:
            dbtype = params['dbtype']
        self.dbtype = dbtype
        if dbtype == 'sqlite':
            self.db = sqlite3.connect(params['database_uri'])
        elif dbtype == 'mysql':
            self.db = mysql.connector.connect(
                host=params['database_host'],
                user=params['username'],
                password=params['password'],
                database=params['database_name']
            )
        else:
            raise ValueError('Unsupported database driver')
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
        """
        Return subnet id from database
        """
        if hasattr(subnet, 'network'):
            # This is an interface
            network = subnet.network
        else:
            # This is a subnet
            network = subnet

        self.cur.execute("SELECT id FROM subnets WHERE subnet='%d' \
                         AND mask='%d'"
                         % (network.network_address,
                            network.prefixlen))
        row = self.cur.fetchone()
        if row is not None:
            return int(row[0])
        return None

    def add_ip(self, ipaddress, dnsname, description):
        """ Adds an IP address in IPAM. ipaddress must be an
        instance of ip_interface. Returns True """
        subnetid = self.find_subnet_id(ipaddress)
        if subnetid is None:
            raise ValueError("Unable to get subnet id from database "
                             "for subnet %s/%s"
                             % (ipaddress.network.network_address,
                                ipaddress.network.prefixlen))
        self.cur.execute("SELECT ip_addr FROM ipaddresses \
                         WHERE ip_addr='%d' AND subnetId=%d"
                         % (ipaddress.ip, subnetid))
        row = self.cur.fetchone()
        if row is not None:
            raise ValueError("IP address %s already registered"
                             % (ipaddress.ip))
        self.cur.execute("INSERT INTO ipaddresses \
                         (subnetId, ip_addr, description, dns_name) \
                         VALUES (%d, '%d', '%s', '%s')"
                         % (subnetid, ipaddress.ip,
                            description, dnsname))
        self.db.commit()
        return True

    def add_next_ip(self, subnet, dnsname, description):
        """ Finds next free ip in subnet, and adds it in IPAM.
        Returns IP address as ip_interface """
        try:
            ipaddress = self.get_next_free_ip(subnet)
            self.add_ip(ipaddress, dnsname, description)
            return ipaddress
        except ValueError as e:
            raise ValueError("Unable to add next IP in %s: %s" % (
                subnet, str(e)))

    def get_next_free_ip(self, subnet):
        """
        Finds next free ip in subnet. Returns IP address as ip_interface
        """
        # Find PHPIPAM subnet id
        subnetid = self.find_subnet_id(subnet)
        if subnetid is None:
            raise ValueError("Unable to get subnet id from database "
                             "for subnet %s/%s"
                             % (subnet.network_address,
                                subnet.prefixlen))
        # Create hosts list in subnet
        subnetips = subnet.hosts()
        # Get allocated ip addresses from database
        usedips = self.get_allocated_ips_by_subnet_id(subnetid)

        subnetips = set(subnetips)
        usedips = set(usedips)
        # Compute the difference between sets, aka available ip addresses set
        availableips = subnetips.difference(usedips)
        # Make a list from the set so we can sort it
        availableips = list(availableips)
        availableips.sort()
        if len(availableips) <= 0:
            raise ValueError("Subnet %s/%s is full"
                             % (subnet.network_address,
                                subnet.prefixlen))
        # Return first available ip address in the list
        return ip_interface("%s/%d" % (availableips[0],
                                       subnet.prefixlen))

    def get_allocated_ips_by_subnet_id(self, subnetid):
        self.cur.execute("SELECT ip_addr FROM ipaddresses \
                         WHERE subnetId=%d ORDER BY ip_addr ASC"
                         % (subnetid))
        iplist = [ip_address(int(ip[0])) for ip in self.cur]
        return iplist

    def add_next_subnet(self, parent_subnet, prefixlen, description):
        """
        Find a subnet prefixlen-wide in parent_subnet, insert it into IPAM,
        and return it.
        """
        if prefixlen <= parent_subnet.prefixlen:
            raise ValueError('Parent subnet {} is too small to add new '
                             'subnet with prefixlen {}!'
                             ''.format(parent_subnet, prefixlen))

        parent_subnet_id = self.find_subnet_id(parent_subnet)
        if not parent_subnet_id:
            raise ValueError('Unable to get subnet id from database '
                             'for parent subnet {}'.format(parent_subnet))

        parent_subnet_used_ips = self.get_allocated_ips_by_subnet_id(
            parent_subnet_id)
        if len(parent_subnet_used_ips):
            raise ValueError('Parent subnet {} must not contain any '
                             'allocated IP address!'.format(parent_subnet))

        subnet = self._get_next_free_subnet(parent_subnet, parent_subnet_id,
                                            prefixlen)
        if not subnet:
            raise ValueError('No more space to add a new subnet with '
                             'prefixlen {} in {}!'.format(
                                prefixlen, parent_subnet))

        # Everything is in order, insert our subnet in IPAM
        self.cur.execute(
            'INSERT INTO subnets '
            '(subnet, mask, sectionId, description, vrfId, '
            'masterSubnetId, vlanId, permissions) '
            'VALUES (\'{:d}\', \'{}\', \'{}\', \'{}\', '
            '\'{}\', \'{}\', \'{}\', \'{}\')'.format(
                int(subnet.network_address),
                subnet.prefixlen,
                self.section_id,
                description,
                self.subnet_options['vrf_id'],
                parent_subnet_id,
                self.subnet_options['vlan_id'],
                self.subnet_options['permissions']))
        return subnet

    def _get_next_free_subnet(self, subnet, subnet_id, prefixlen):
        """
        Find next free prefixlen-wide subnet in a given subnet.
        """
        allocated_subnets = self._get_allocated_subnets(
            subnet_id, prefixlen)

        for candidate_subnet in subnet.subnets(new_prefix=prefixlen):
            is_overlapping = False
            # A candidate subnet is free if it doesn't overlap any other
            # allocated subnet
            for allocated_subnet in allocated_subnets:
                if candidate_subnet.overlaps(allocated_subnet):
                    is_overlapping = True
                    # Since one subnet is overlapping, don't check the others
                    break
            if not is_overlapping:
                return candidate_subnet
        return None

    def _get_allocated_subnets(self, subnet_id, prefixlen):
        """
        Return list of unavailable children subnets in a parent subnet,
        given its id.
        """
        self.cur.execute('SELECT subnet, mask FROM subnets '
                         'WHERE masterSubnetId={} '
                         'ORDER BY subnet ASC'.format(subnet_id))

        allocated_subnets = [
            ip_network('{}/{}'.format(ip_address(int(row[0])), int(row[1])))
            for row in self.cur
        ]
        return allocated_subnets

    def delete_ip(self, ipaddress):
        """Delete an IP address in IPAM. ipaddress must be an
        instance of ip_interface with correct prefix length.
        """
        subnetid = self.find_subnet_id(ipaddress)
        if subnetid is None:
            raise ValueError("Unable to get subnet id from database "
                             "for subnet %s/%s"
                             % (ipaddress.network.network_address,
                                ipaddress.network.prefixlen))
        self.cur.execute("SELECT ip_addr FROM ipaddresses \
                         WHERE ip_addr='%d' AND subnetId=%d"
                         % (ipaddress.ip, subnetid))
        row = self.cur.fetchone()
        if row is None:
            raise ValueError("IP address %s not present"
                             % (ipaddress.ip))
        self.cur.execute("DELETE from ipaddresses \
                         WHERE ip_addr='%d' AND subnetId=%d"
                         % (ipaddress.ip, subnetid))
        self.db.commit()
        return True

    def _empty_subnet(self, subnet_id):
        """
        Delete all IP addresses within a subnet
        """
        self.cur.execute("DELETE FROM ipaddresses \
                         WHERE subnetId = %d"
                         % subnet_id)

    def delete_subnet(self, subnet, empty_subnet=False):
        """
        Delete a subnet in IPAM. subnet must be an
        instance of ip_network with correct prefix length.
        If empty_subnet is True, we will remove all IP addresses
        in the subnet. Otherwise, we will raise an exception.
        """
        subnet_id = self.find_subnet_id(subnet)
        if subnet_id is None:
            raise ValueError("Unable to get subnet id from database"
                             "for subnet %s/%s"
                             % (subnet.network_address,
                                subnet.prefixlen))
        ip_list = self.get_allocated_ips_by_subnet_id(subnet_id)
        if ip_list:
            # We have IP addresses in our subnet
            if empty_subnet:
                self._empty_subnet(subnet_id)
            else:
                raise ValueError("Subnet %s/%s is not empty"
                                 % (subnet.network_address,
                                    subnet.prefixlen))
        children_subnets = self._get_allocated_subnets(subnet_id)
        if children_subnets:
            # The subnet we are trying to delete is master for other subnets
            raise ValueError("Subnet %s/%s has children subnets"
                             % (subnet.network_address,
                                subnet.prefixlen))
        self.cur.execute("DELETE FROM subnets \
                         WHERE id=%d"
                         % subnet_id)
        self.db.commit()
        return True

    def get_hostname_by_ip(self, ip):
        self.cur.execute("SELECT dns_name FROM ipaddresses \
                         WHERE ip_addr='%d'"
                         % ip)
        row = self.cur.fetchone()
        if row is not None:
            return row[0]
        return None

    def get_description_by_ip(self, ip):
        self.cur.execute("SELECT description FROM ipaddresses \
                         WHERE ip_addr='%d'"
                         % ip)
        row = self.cur.fetchone()
        if row is not None:
            return row[0]
        return None

    def get_ipnetwork_list_by_desc(self, description):
        """
        Wrapper for backward compatibility
        """
        return self.get_ip_interface_list_by_desc(description)

    def get_ip_interface_list_by_desc(self, description):
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
            net_ip_address = ip_address(int(row[0]))
            item['ip'] = ip_interface(str(net_ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            item['vlan_id'] = row[5]
            iplist.append(item)
        return iplist

    def get_ipnetwork_by_desc(self, description):
        """
        Wrapper for backward compatibility
        """
        return self.get_ip_interface_by_desc(description)

    def get_ip_interface_by_desc(self, description):
        iplist = self.get_ip_interface_list_by_desc(description)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_ipnetwork_list_by_subnet_name(self, subnet_name):
        """
        Wrapper for backward compatibility
        """
        return self.get_ip_interface_list_by_subnet_name(subnet_name)

    def get_ip_interface_list_by_subnet_name(self, subnet_name):
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
            net_ip_address = ip_address(int(row[0]))
            item['ip'] = ip_interface(str(net_ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            iplist.append(item)
        return iplist

    def get_ipnetwork_by_subnet_name(self, subnet_name):
        """
        Wrapper for backward compatibility
        """
        return self.get_ip_interface_by_subnet_name(subnet_name)

    def get_ip_interface_by_subnet_name(self, subnet_name):
        iplist = self.get_ip_interface_list_by_subnet_name(subnet_name)
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
            item['ip'] = ip_address(int(row[0]))
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
            subnet = str(ip_address(int(row[0])))
            item['subnet'] = ip_network("%s/%s" % (subnet, row[1]))
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
            subnet = str(ip_address(int(row[0])))
            item['subnet'] = ip_network("%s/%s" % (subnet, row[1]))
            item['description'] = row[2]
            return item
        return None

    def get_num_ips_by_desc(self, description):
        self.cur.execute("SELECT COUNT(ip_addr) FROM ipaddresses \
                         WHERE description LIKE '%s'\
                              AND state = '1'"
                         % (description))
        row = self.cur.fetchone()
        return int(row[0])

    def get_num_subnets_by_desc(self, description):
        self.cur.execute("SELECT COUNT(subnet) FROM subnets \
                         WHERE description LIKE '%s'"
                         % description)
        row = self.cur.fetchone()
        return int(row[0])

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
