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

LOCK_NAME = 'ipam_client_lock'
LOCK_TIMEOUT = 5


class MySQLLock(object):
    def __init__(self, ipam):
        self.ipam = ipam

    def __enter__(self):
        if self.ipam.dbtype == 'mysql':
            # Disable autocommit during writes for transactional behavior
            self.ipam.db.autocommit = False
            self.ipam.db.start_transaction(isolation_level='SERIALIZABLE')
            self.ipam.cur.execute('SELECT GET_LOCK("{}", {})'.format(
                LOCK_NAME, LOCK_TIMEOUT))
            row = self.ipam.cur.fetchone()

            if not row[0]:
                e = 'Could not obtain lock within {} seconds.'.format(
                    LOCK_TIMEOUT)
                raise RuntimeError(e)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if self.ipam.dbtype == 'mysql':
            if exception_type:
                self.ipam.db.rollback()
            else:
                self.ipam.db.commit()
            self.ipam.cur.execute('SELECT RELEASE_LOCK("{}")'.format(
                LOCK_NAME))
            self.ipam.db.autocommit = True


class PHPIPAM(AbstractIPAM):

    def __init__(self, params):
        dbtype = DEFAULT_IPAM_DB_TYPE
        subnet_options = DEFAULT_SUBNET_OPTIONS.copy()
        self.hostname_db_field = 'hostname'
        self.used_ip_state = 2
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
            self.cur = self.db.cursor()
        elif dbtype == 'mysql':
            self.db = mysql.connector.connect(
                host=params['database_host'],
                user=params['username'],
                password=params['password'],
                database=params['database_name']
            )
            # Enable autocommit for reads to prevent entering transaction
            self.db.autocommit = True
            self.cur = self.db.cursor(buffered=True)
        else:
            raise ValueError('Unsupported database driver')
        self.set_section_id_by_name(section_name)

        if self._get_version() < 1.32:
            # Older PHPIPAM version use `dns_name` field instead of `hostname`
            self.hostname_db_field = 'dns_name'
            self.used_ip_state = 1

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

    def _get_version(self):
        self.cur.execute('SELECT version FROM settings LIMIT 1')
        row = self.cur.fetchone()
        if row is None:
            raise ValueError('Could not retrieve version from DB')
        return float(row[0])

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

        raise ValueError(
            "Unable to get subnet id from database "
            "for subnet {}".format(subnet)
        )

    def add_ip(self, ipaddress, hostname, description, mac=None):
        """ Adds an IP address in IPAM. ipaddress must be an
        instance of ip_interface. Returns True """
        with MySQLLock(self):
            subnetid = self.find_subnet_id(ipaddress)
            self.cur.execute("SELECT ip_addr FROM ipaddresses \
                             WHERE ip_addr='%d' AND subnetId=%d LIMIT 1"
                             % (ipaddress.ip, subnetid))
            row = self.cur.fetchone()
            if row is not None:
                raise ValueError("IP address %s already registered"
                                 % (ipaddress.ip))
            self.cur.execute("INSERT INTO ipaddresses \
                             (subnetId, ip_addr, description, %s, mac) \
                             VALUES (%d, '%d', '%s', '%s', '%s')"
                             % (self.hostname_db_field, subnetid,
                                ipaddress.ip, description, hostname,
                                '' if mac is None else mac))
        return True

    def add_next_ip(self, subnet, hostname, description, mac=None, allow_duplicates=True):
        """ Finds next free ip in subnet, and adds it in IPAM.
        If allow_duplicates is False, lookup for IP matching hostname and if any,
        return it instead of allocating a new one.
        Returns IP address as ip_interface """
        try:
            with MySQLLock(self):
                if not allow_duplicates:
                    ipaddress = None
                    try:
                        ipaddress = self.get_ip_by_desc_and_subnet(description, subnet.network_address)
                    except ValueError:
                        pass
                    if ipaddress:
                        return ip_interface("%s/%d" % (ipaddress, subnet.prefixlen))
                ipaddress = self.get_next_free_ip(subnet)
                subnetid = self.find_subnet_id(ipaddress)
                self.cur.execute("INSERT INTO ipaddresses \
                                 (subnetId, ip_addr, description, %s, mac) \
                                 VALUES (%d, '%d', '%s', '%s', '%s')"
                                 % (self.hostname_db_field, subnetid,
                                    ipaddress.ip, description, hostname,
                                    '' if mac is None else mac))
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
        # Get allocated ip addresses from database
        usedips = self.get_allocated_ips_by_subnet_id(subnetid)

        for candidate_ip in subnet.hosts():
            if candidate_ip not in usedips:
                # Return first available ip address in the subnet
                return ip_interface("%s/%d" % (candidate_ip,
                                               subnet.prefixlen))
        raise ValueError("Subnet %s/%s is full"
                         % (subnet.network_address,
                            subnet.prefixlen))

    def get_allocated_ips_by_subnet_id(self, subnetid):
        request_suffix = ''
        if self.dbtype == 'mysql':
            request_suffix = ' FOR UPDATE'
        self.cur.execute('SELECT ip_addr FROM ipaddresses '
                         'WHERE subnetId={} ORDER BY ip_addr ASC{}'
                         ''.format(subnetid, request_suffix))
        iplist = [ip_address(int(ip[0])) for ip in self.cur]
        return iplist

    def add_top_level_subnet(self, subnet, description):
        """
        Add top level (without any parent) subnet.

        :param subnet: subnet (ip_network format)
        :param description: subnet description
        :return: True
        """
        with MySQLLock(self):
            # Check if subnet exist
            self.cur.execute("SELECT subnet FROM subnets \
                             WHERE subnet='{}'"
                             .format(int(subnet.network_address)))
            row = self.cur.fetchone()
            if row is not None:
                raise ValueError("Subnet {} already registered".format(subnet))

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
                    0,
                    self.subnet_options['vlan_id'],
                    self.subnet_options['permissions']))

        return True

    def add_subnet(self, subnet, parent_subnet, description):
        """
        Add a subnet if can be inserted in parent subnet.
        """
        parent_subnet_id = self.find_subnet_id(parent_subnet)

        if not subnet.overlaps(parent_subnet):
            raise ValueError('Subnet {} is not a child of {}'.format(
                subnet,
                parent_subnet,
            ))

        if subnet.prefixlen < parent_subnet.prefixlen:
            raise ValueError('Candidate subnet {} bigger than {}'.format(
                subnet,
                parent_subnet,
            ))

        children_subnets = self.get_children_subnet_list(parent_subnet)
        for children_subnet in children_subnets:
            if children_subnet['subnet'].overlaps(subnet):
                raise ValueError('Candidate subnet overlaps with {}'.format(
                    children_subnet['subnet']
                ))

        parent_subnet_used_ips = self.get_allocated_ips_by_subnet_id(
            parent_subnet_id)
        if len(parent_subnet_used_ips) > 0:
            raise ValueError('Parent subnet {} must not contain any '
                             'allocated IP address!'.format(parent_subnet))

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

    def add_next_subnet(self, parent_subnet, prefixlen, description):
        """
        Find a subnet prefixlen-wide in parent_subnet, insert it into IPAM,
        and return it.
        """
        with MySQLLock(self):
            if prefixlen <= parent_subnet.prefixlen:
                raise ValueError('Parent subnet {} is too small to add new '
                                 'subnet with prefixlen {}!'
                                 ''.format(parent_subnet, prefixlen))

            try:
                parent_subnet_id = self.find_subnet_id(parent_subnet)
            except ValueError:
                raise ValueError('Unable to get subnet id from database '
                                 'for parent subnet {}'.format(parent_subnet))

            parent_subnet_used_ips = self.get_allocated_ips_by_subnet_id(
                parent_subnet_id)
            if len(parent_subnet_used_ips):
                raise ValueError('Parent subnet {} must not contain any '
                                 'allocated IP address!'
                                 ''.format(parent_subnet))

            subnet = self._get_next_free_subnet(parent_subnet,
                                                parent_subnet_id,
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
        allocated_subnets = self._get_allocated_subnets(subnet_id)

        for candidate_subnet in subnet.subnets(new_prefix=prefixlen):
            # A candidate subnet is free if it doesn't overlap any other
            # allocated subnet
            for allocated_subnet in allocated_subnets:
                if candidate_subnet.overlaps(allocated_subnet):
                    # Since one subnet is overlapping, don't check the others
                    break
            else:
                return candidate_subnet
        return None

    def _get_allocated_subnets(self, subnet_id):
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

    def edit_ip_description(self, ipaddress, description):
        """Edit an IP address description in IPAM. ipaddress must be an
        instance of ip_interface with correct prefix length.
        """
        with MySQLLock(self):
            subnetid = self.find_subnet_id(ipaddress)
            self.cur.execute("SELECT ip_addr FROM ipaddresses \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (ipaddress.ip, subnetid))
            row = self.cur.fetchone()
            if row is None:
                raise ValueError("IP address %s not present"
                                 % (ipaddress.ip))
            self.cur.execute("UPDATE ipaddresses \
                             SET description='%s' \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (description, ipaddress.ip, subnetid))
        return True

    def edit_ip_hostname(self, ipaddress, hostname):
        """Edit an IP address hostname in IPAM. ipaddress must be an
        instance of ip_interface with correct prefix length.
        """
        with MySQLLock(self):
            subnetid = self.find_subnet_id(ipaddress)
            self.cur.execute("SELECT ip_addr FROM ipaddresses \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (ipaddress.ip, subnetid))
            row = self.cur.fetchone()
            if row is None:
                raise ValueError("IP address %s not present"
                                 % (ipaddress.ip))
            self.cur.execute("UPDATE ipaddresses \
                             SET %s='%s' \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (self.hostname_db_field, hostname,
                                ipaddress.ip, subnetid))
        return True

    def edit_ip_mac(self, ipaddress, mac):
        """Edit an IP address MAC in IPAM. ipaddress must be an
        instance of ip_interface with correct prefix length.
        """
        with MySQLLock(self):
            subnetid = self.find_subnet_id(ipaddress)
            self.cur.execute("SELECT ip_addr FROM ipaddresses \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (ipaddress.ip, subnetid))
            row = self.cur.fetchone()
            if row is None:
                raise ValueError("IP address %s not present"
                                 % (ipaddress.ip))
            self.cur.execute("UPDATE ipaddresses \
                             SET mac='%s' \
                             WHERE ip_addr='%d' AND subnetId=%d"
                             % (mac, ipaddress.ip, subnetid))
        return True

    def edit_subnet_description(self, subnet, description):
        """Edit a subnet description in IPAM. subnet must be an
        instance of ip_network and the description must not be
        empty.
        """
        if not description:
            raise ValueError("The provided description is empty")

        with MySQLLock(self):
            subnetid = self.find_subnet_id(subnet)
            self.cur.execute(
                "UPDATE subnets "
                "SET description='{}'"
                "WHERE id={}".format(description, subnetid)
            )

    def delete_ip(self, ipaddress):
        """Delete an IP address in IPAM. ipaddress must be an
        instance of ip_interface with correct prefix length.
        """
        with MySQLLock(self):
            subnetid = self.find_subnet_id(ipaddress)
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
        return True

    def delete_subnet(self, subnet, empty_subnet=False):
        """
        Delete a subnet in IPAM. subnet must be an
        instance of ip_network with correct prefix length.
        If empty_subnet is True, we will remove all IP addresses
        in the subnet. Otherwise, we will raise an exception.
        """
        with MySQLLock(self):
            subnet_id = self.find_subnet_id(subnet)
            ip_list = self.get_allocated_ips_by_subnet_id(subnet_id)
            if ip_list:
                # We have IP addresses in our subnet
                if empty_subnet:
                    self.cur.execute("DELETE FROM ipaddresses \
                                     WHERE subnetId = %d"
                                     % subnet_id)
                else:
                    raise ValueError("Subnet %s/%s is not empty"
                                     % (subnet.network_address,
                                        subnet.prefixlen))
            children_subnets = self._get_allocated_subnets(subnet_id)
            if children_subnets:
                # The subnet we are trying to delete
                # is master for other subnets
                raise ValueError("Subnet %s/%s has children subnets"
                                 % (subnet.network_address,
                                    subnet.prefixlen))
            self.cur.execute("DELETE FROM subnets \
                             WHERE id=%d"
                             % subnet_id)
        return True

    def get_ip(self, ip):
        self.cur.execute("SELECT ip.ip_addr,ip.description,ip.%s,\
                              s.mask,s.description,v.number,ip.mac\
                          FROM ipaddresses ip\
                          LEFT JOIN subnets s ON\
                              ip.subnetId = s.id\
                          LEFT JOIN vlans v ON\
                              s.vlanId = v.vlanId\
                          WHERE ip.ip_addr = '%d'\
                              AND ip.state = %d"
                         % (self.hostname_db_field, ip, self.used_ip_state))
        row = self.cur.fetchone()
        if row is not None:
            item = {}
            net_ip_address = ip_address(int(row[0]))
            item['ip'] = ip_interface(str(net_ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            item['vlan_id'] = row[5]
            item['mac'] = row[6]
            return item
        return None

    def get_hostname_by_ip(self, ip):
        self.cur.execute("SELECT %s FROM ipaddresses \
                         WHERE ip_addr='%d'"
                         % (self.hostname_db_field, ip))
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

    def get_mac_by_ip(self, ip):
        self.cur.execute("SELECT mac FROM ipaddresses \
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
        self.cur.execute("SELECT ip.ip_addr,ip.description,ip.%s,\
                              s.mask,s.description,v.number,ip.mac\
                          FROM ipaddresses ip\
                          LEFT JOIN subnets s ON\
                              ip.subnetId = s.id\
                          LEFT JOIN vlans v ON\
                              s.vlanId = v.vlanId\
                          WHERE ip.description LIKE '%s'\
                              AND ip.state = %d"
                         % (self.hostname_db_field,
                            description,
                            self.used_ip_state))
        iplist = list()
        for row in self.cur:
            item = {}
            net_ip_address = ip_address(int(row[0]))
            item['ip'] = ip_interface(str(net_ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            item['vlan_id'] = row[5]
            item['mac'] = row[6]
            iplist.append(item)
        return iplist

    def get_subnet_with_ips(self, subnet):
        """"
        Returns a subnet with all its allocated ip addresses
        """

        ipam_subnet = {}

        self.cur.execute('SELECT ip.ip_addr,ip.description,ip.{},ip.state,'
                         's.description,s.vlanId,ip.mac '
                         'FROM ipaddresses ip LEFT JOIN subnets s '
                         'ON ip.subnetId = s.id '
                         "WHERE s.subnet='{}' AND s.mask='{}'"
                         ''.format(self.hostname_db_field,
                                   int(subnet.network_address),
                                   subnet.prefixlen))
        iplist = list()
        for row in self.cur:
            if not ipam_subnet:
                ipam_subnet['subnet'] = subnet
                ipam_subnet['description'] = row[4]
                ipam_subnet['vlan_id'] = row[5]
            item = {}
            item['ip'] = ip_address(int(row[0]))
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['state'] = row[3]
            item['mac'] = row[6]
            iplist.append(item)
        ipam_subnet['ips'] = iplist
        return ipam_subnet

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
        self.cur.execute("SELECT ip.ip_addr,ip.description,ip.%s,\
                              s.mask,s.description,ip.mac\
                          FROM ipaddresses ip\
                          LEFT JOIN subnets s ON\
                              ip.subnetId = s.id\
                          WHERE s.description LIKE '%s'\
                              AND ip.state = %d"
                         % (self.hostname_db_field,
                            subnet_name,
                            self.used_ip_state))
        iplist = list()
        for row in self.cur:
            item = {}
            net_ip_address = ip_address(int(row[0]))
            item['ip'] = ip_interface(str(net_ip_address) + "/" + row[3])
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['subnet_name'] = row[4]
            item['mac'] = row[5]
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
        self.cur.execute("SELECT ip_addr,description,%s,state,mac \
                         FROM ipaddresses \
                         WHERE description LIKE '%s'"
                         % (self.hostname_db_field, description))
        iplist = list()
        for row in self.cur:
            item = {}
            item['ip'] = ip_address(int(row[0]))
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['state'] = int(row[3])
            item['mac'] = row[4]
            iplist.append(item)
        return iplist

    def get_ip_by_desc(self, description):
        iplist = self.get_ip_list_by_desc(description)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_ip_by_desc_and_subnet(self, description, subnet):
        self.cur.execute("SELECT id \
                         FROM subnets \
                         WHERE subnet = '%i'" % int(ip_address((subnet))))
        row = self.cur.fetchone()
        if row is not None:
            subnet_id = int(row[0])
        else:
            raise ValueError(
                "Unable to get subnet id from database "
                "for this subnet: {}".format(subnet)
            )

        self.cur.execute("SELECT ip_addr \
                         FROM ipaddresses \
                         WHERE description LIKE '%s' AND subnetId = '%i'"
                         % (description, subnet_id))

        row = self.cur.fetchone()
        if row is not None:
            return ip_address(int(row[0]))

        raise ValueError(
            "Unable to get {} in the subnet {} from database".format(
                description, subnet)
        )

    def get_ip_list_by_mac(self, mac):
        self.cur.execute("SELECT ip_addr,description,%s,state,mac \
                         FROM ipaddresses \
                         WHERE mac LIKE '%s'"
                         % (self.hostname_db_field, mac))
        iplist = list()
        for row in self.cur:
            item = {}
            item['ip'] = ip_address(int(row[0]))
            item['description'] = row[1]
            item['dnsname'] = row[2]
            item['state'] = int(row[3])
            item['mac'] = row[4]
            iplist.append(item)
        return iplist

    def get_ip_by_mac(self, mac):
        iplist = self.get_ip_list_by_mac(mac)
        if iplist == []:
            return None
        else:
            return iplist[0]

    def get_children_subnet_list(self, parent_subnet):
        netlist = list()
        parent_subnet_id = self.find_subnet_id(parent_subnet)
        self.cur.execute("SELECT subnet,mask,description,vlanId FROM subnets \
                         WHERE masterSubnetId = '%i'"
                         % parent_subnet_id)
        for row in self.cur:
            item = {}
            subnet = str(ip_address(int(row[0])))
            item['subnet'] = ip_network("%s/%s" % (subnet, row[1]))
            item['description'] = row[2]
            item['vlan_id'] = row[3]
            netlist.append(item)
        return netlist

    def get_subnet(self, subnet):
        self.cur.execute("SELECT subnet,mask,description,vlanId FROM subnets \
                          where subnet = '{}' AND mask = '{}'".format(int(subnet.network_address),
                                                                      subnet.prefixlen))
        row = self.cur.fetchone()
        if row is not None:
            item = {}
            subnet = str(ip_address(int(row[0])))
            netmask = row[1]
            item['subnet'] = ip_network("{}/{}".format(subnet, netmask))
            item['description'] = row[2]
            item['vlan_id'] = row[3]
            return item
        return None

    def get_subnet_list_by_desc(self, description):
        self.cur.execute("SELECT subnet,mask,description,vlanId FROM subnets \
                         WHERE description LIKE '%s'"
                         % description)
        netlist = list()
        for row in self.cur:
            item = {}
            subnet = str(ip_address(int(row[0])))
            netmask = row[1]
            if netmask == '':
                netmask = 0
            item['subnet'] = ip_network("%s/%s" % (subnet, netmask))
            item['description'] = row[2]
            item['vlan_id'] = row[3]
            netlist.append(item)
        return netlist

    def get_subnet_by_desc(self, description):
        subnetlist = self.get_subnet_list_by_desc(description)
        if subnetlist == []:
            return None
        else:
            return subnetlist[0]

    def get_subnet_by_id(self, subnetid):
        self.cur.execute("SELECT subnet,mask,description,vlanId FROM subnets \
                         WHERE id=%d"
                         % subnetid)
        row = self.cur.fetchone()
        if row is not None:
            item = {}
            subnet = str(ip_address(int(row[0])))
            item['subnet'] = ip_network("%s/%s" % (subnet, row[1]))
            item['description'] = row[2]
            item['vlan_id'] = row[3]
            return item
        return None

    def get_num_ips_by_desc(self, description):
        self.cur.execute("SELECT COUNT(ip_addr) FROM ipaddresses \
                         WHERE description LIKE '%s'\
                              AND state = %d"
                         % (description, self.used_ip_state))
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
