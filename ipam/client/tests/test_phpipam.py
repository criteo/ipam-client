from __future__ import unicode_literals
import mysql.connector
import os
import pytest
import tempfile
import sqlite3
from ipam.client.backends.phpipam import PHPIPAM
from ipaddress import ip_address, ip_interface, ip_network


@pytest.fixture
def testdb(request):
    """Test SQLite instance."""
    _dbfile = tempfile.NamedTemporaryFile(prefix='test-phpipam',
                                          suffix='.db', delete=False)
    _dbfilename = _dbfile.name
    _dbfile.close()

    conn = sqlite3.connect(_dbfilename)
    cur = conn.cursor()

    f = open(os.path.dirname(os.path.realpath(__file__)) + '/data/db.sql')
    sql = f.read()
    cur.executescript(sql)

    conn.commit()
    conn.close()

    def testdbteardown():
        os.unlink(_dbfilename)

    request.addfinalizer(testdbteardown)
    return _dbfilename


@pytest.fixture
def testphpipam(testdb):
    """Test PHPIPAM instance."""
    params = {'section_name': 'Production', 'dbtype': 'sqlite',
              'database_uri': testdb}

    return PHPIPAM(params)


def test_db_fail():
    params = {'section_name': 'Test', 'username': 'test',
              'database_host': 'localhost', 'database_name': 'test',
              'password': 'test', 'database_uri': 'testdb'}
    with pytest.raises(mysql.connector.Error):
        PHPIPAM(params)

    params['dbtype'] = 'test'
    with pytest.raises(ValueError):
        PHPIPAM(params)


def test_set_section_id(testphpipam):
    testphpipam.set_section_id(42)
    assert testphpipam.section_id == 42
    assert testphpipam.get_section_id() == 42


def test_set_section_id_by_name(testphpipam):
    testphpipam.set_section_id_by_name('Management')
    assert testphpipam.section_id == 4
    with pytest.raises(ValueError) as excinfo:
        testphpipam.set_section_id_by_name('Unknown')
    assert "Can't get section id matching" in str(excinfo.value)


def test_get_section_id(testphpipam):
    assert testphpipam.section_id == 2


def test_find_subnet_id(testphpipam):
    assert testphpipam.find_subnet_id(ip_interface('10.42.0.0/16')) is None
    assert testphpipam.find_subnet_id(ip_interface('10.2.0.0/29')) == 2


def test_add_ip(testphpipam):
    ip = ip_interface('10.1.0.1/28')
    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_ip(ip, 'err', 'err')
    assert "already registered" in str(excinfo.value)

    ip = ip_interface('10.1.0.4/28')
    description = 'add_ip generated ip 1'
    dnsname = 'add_ip generated-ip-1'
    assert testphpipam.add_ip(ip, dnsname, description) is True

    ip = ip_interface('10.42.0.1/28')
    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_ip(ip, 'err', 'err')
    assert "Unable to get subnet id" in str(excinfo.value)


def test_add_next_ip(testphpipam):
    subnet = ip_network('10.1.0.0/28')
    for i in list(range(4, 7)) + list(range(11, 15)):
        description = 'add_next_ip generated ip %d' % i
        dnsname = 'add_next_ip generated-ip-%d' % i
        ipaddr = ip_address('10.1.0.%d' % i)

        ip = testphpipam.add_next_ip(subnet, dnsname, description)
        assert ip.ip == ipaddr
        assert ip.network.prefixlen == 28
        testip = testphpipam.get_ip_by_desc(description)
        assert testip['ip'] == ipaddr
        assert testip['dnsname'] == dnsname
        assert testip['description'] == description

    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_next_ip(subnet, 'err', 'err')
    assert "is full" in str(excinfo.value)

    subnet = ip_network('10.2.0.0/29')
    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_next_ip(subnet, 'err', 'err')
    assert "is full" in str(excinfo.value)

    subnet = ip_network('10.3.0.0/30')
    description = 'add_next_ip generated ip 16'
    dnsname = 'add_next_ip generated-ip-16'
    ipaddr = ip_address('10.3.0.1')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 30
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    subnet = ip_network('10.4.0.0/31')
    description = 'add_next_ip generated ip 17'
    dnsname = 'add_next_ip generated-ip-17'
    ipaddr = ip_address('10.4.0.0')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 31
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    subnet = ip_network('10.5.0.0/31')
    description = 'add_next_ip generated ip 18'
    dnsname = 'add_next_ip generated-ip-18'
    ipaddr = ip_address('10.5.0.1')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 31
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_next_ip(subnet, 'err', 'err')
    assert "is full" in str(excinfo.value)

    subnet = ip_network('2001::40/125')
    description = 'add_next_ip generated ip 19'
    dnsname = 'add_next_ip generated-ip-19'
    ipaddr = ip_address('2001::41')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 20'
    dnsname = 'add_next_ip generated-ip-20'
    ipaddr = ip_address('2001::42')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 21'
    dnsname = 'add_next_ip generated-ip-21'
    ipaddr = ip_address('2001::43')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 22'
    dnsname = 'add_next_ip generated-ip-22'
    ipaddr = ip_address('2001::44')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 23'
    dnsname = 'add_next_ip generated-ip-21'
    ipaddr = ip_address('2001::45')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 24'
    dnsname = 'add_next_ip generated-ip-22'
    ipaddr = ip_address('2001::46')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 25'
    dnsname = 'add_next_ip generated-ip-22'
    ipaddr = ip_address('2001::47')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 125
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_next_ip(subnet, 'err', 'err')
    assert "is full" in str(excinfo.value)

    subnet = ip_network('2001::50/127')
    description = 'add_next_ip generated ip 26'
    dnsname = 'add_next_ip generated-ip-23'
    ipaddr = ip_address('2001::50')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 127
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    description = 'add_next_ip generated ip 27'
    dnsname = 'add_next_ip generated-ip-24'
    ipaddr = ip_address('2001::51')
    ip = testphpipam.add_next_ip(subnet, dnsname, description)
    assert ip.ip == ipaddr
    assert ip.network.prefixlen == 127
    testip = testphpipam.get_ip_by_desc(description)
    assert testip['ip'] == ipaddr
    assert testip['dnsname'] == dnsname
    assert testip['description'] == description

    with pytest.raises(ValueError) as excinfo:
        testphpipam.add_next_ip(subnet, 'err', 'err')
    assert "is full" in str(excinfo.value)


def test_delete_ip(testphpipam):
    iplist = testphpipam.get_ip_list_by_desc('test ip #2')
    assert iplist == [{'ip': ip_address('10.1.0.2'),
                       'description': 'test ip #2',
                       'dnsname': 'test-ip-2'}]
    testphpipam.delete_ip(ip_interface('10.1.0.2/28'))
    iplist = testphpipam.get_ip_list_by_desc('test ip #2')
    assert iplist == []

    with pytest.raises(ValueError):
        testphpipam.delete_ip(ip_interface('10.1.0.2/28'))

    with pytest.raises(ValueError):
        testphpipam.delete_ip(ip_interface('10.1.0.42/28'))


def test_get_next_free_ip(testphpipam):
    ip = testphpipam.get_next_free_ip(ip_network('10.1.0.0/28'))
    assert ip.ip == ip_address('10.1.0.4')
    assert ip.network.prefixlen == 28

    with pytest.raises(ValueError) as excinfo:
        testphpipam.get_next_free_ip(ip_network('10.2.0.0/29'))
    assert "is full" in str(excinfo.value)

    ip = testphpipam.get_next_free_ip(ip_network('10.3.0.0/30'))
    assert ip.ip == ip_address('10.3.0.1')
    assert ip.network.prefixlen == 30

    ip = testphpipam.get_next_free_ip(ip_network('10.4.0.0/31'))
    assert ip.ip == ip_address('10.4.0.0')
    assert ip.network.prefixlen == 31

    ip = testphpipam.get_next_free_ip(ip_network('10.5.0.0/31'))
    assert ip.ip == ip_address('10.5.0.1')
    assert ip.network.prefixlen == 31

    with pytest.raises(ValueError) as excinfo:
        testphpipam.get_next_free_ip(ip_network('10.42.0.0/29'))
    assert "Unable to get subnet id from database" in str(excinfo.value)


def test_get_subnet_by_id(testphpipam):
    assert testphpipam.get_subnet_by_id(42) is None
    testsubnet = testphpipam.get_subnet_by_id(3)
    assert testsubnet['subnet'] == ip_network('10.3.0.0/30')
    assert testsubnet['description'] == 'TST /30 SUBNET'


def test_get_allocated_ips_by_subnet_id(testphpipam):
    assert testphpipam.get_allocated_ips_by_subnet_id(4) == []
    iplist = [ip_address('10.1.0.1'),
              ip_address('10.1.0.2'),
              ip_address('10.1.0.3'),
              ip_address('10.1.0.7'),
              ip_address('10.1.0.8'),
              ip_address('10.1.0.9'),
              ip_address('10.1.0.10')]
    assert testphpipam.get_allocated_ips_by_subnet_id(1) == iplist


def test_get_ip_by_desc(testphpipam):
    assert testphpipam.get_ip_by_desc('unknown ip') is None

    testip = testphpipam.get_ip_by_desc('test ip #2')
    assert testip['ip'] == ip_address('10.1.0.2')
    assert testip['description'] == 'test ip #2'
    assert testip['dnsname'] == 'test-ip-2'

    testip = testphpipam.get_ip_by_desc('test ip group 1')
    assert testip['ip'] == ip_address('10.2.0.1')
    assert testip['description'] == 'test ip group 1'
    assert testip['dnsname'] == 'test-ip-8'


def test_get_ip_interface_by_desc(testphpipam):
    assert testphpipam.get_ip_by_desc('unknown ip') is None

    testip = testphpipam.get_ip_interface_by_desc('test ip #2')
    assert testip['ip'] == ip_interface('10.1.0.2/28')
    assert testip['description'] == 'test ip #2'
    assert testip['dnsname'] == 'test-ip-2'

    testip = testphpipam.get_ip_interface_by_desc('test ip group 1')
    assert testip['ip'] == ip_interface('10.2.0.1/29')
    assert testip['description'] == 'test ip group 1'
    assert testip['dnsname'] == 'test-ip-8'

    testip = testphpipam.get_ip_interface_by_desc('non-existent ip')
    assert testip is None


def test_get_ipnetwork_by_desc(testphpipam):
    assert testphpipam.get_ipnetwork_by_desc('unknown ip') is None


def test_get_ip_list_by_desc(testphpipam):
    assert testphpipam.get_ip_list_by_desc('unknown ip') == []

    iplist = testphpipam.get_ip_list_by_desc('test ip #2')
    assert iplist == [{'ip': ip_address('10.1.0.2'),
                       'description': 'test ip #2',
                       'dnsname': 'test-ip-2'}]

    iplist = testphpipam.get_ip_list_by_desc('test ip group 1')
    assert iplist == [{'ip': ip_address('10.2.0.1'),
                       'description': 'test ip group 1',
                       'dnsname': 'test-ip-8'},
                      {'ip': ip_address('10.2.0.2'),
                       'description': 'test ip group 1',
                       'dnsname': 'test-ip-9'}]


def test_get_ip_interface_list_by_desc(testphpipam):
    assert testphpipam.get_ip_interface_list_by_desc('unknown ip') == []

    iplist = testphpipam.get_ip_interface_list_by_desc('test ip #2')
    assert iplist == [{'ip': ip_interface('10.1.0.2/28'),
                       'description': 'test ip #2',
                       'dnsname': 'test-ip-2',
                       'subnet_name': 'TEST /28 SUBNET',
                       'vlan_id': 42
                       }]
    iplist = testphpipam.get_ip_interface_list_by_desc('test ip group 1')
    assert iplist == [{'ip': ip_interface('10.2.0.1/29'),
                       'description': 'test ip group 1',
                       'dnsname': 'test-ip-8',
                       'subnet_name': 'TEST FULL /29 SUBNET',
                       'vlan_id': None
                       },
                      {'ip': ip_interface('10.2.0.2/29'),
                       'description': 'test ip group 1',
                       'dnsname': 'test-ip-9',
                       'subnet_name': 'TEST FULL /29 SUBNET',
                       'vlan_id': None}
                      ]


def test_get_ipnetwork_list_by_desc(testphpipam):
    assert testphpipam.get_ipnetwork_list_by_desc('unknown ip') == []


def test_get_ip_interface_by_subnet_name(testphpipam):
    ip = testphpipam.get_ip_interface_by_subnet_name('TEST%')
    assert ip == {'description': u'test ip #1',
                  'dnsname': u'test-ip-1',
                  'ip': ip_interface('10.1.0.1/28'),
                  'subnet_name': u'TEST /28 SUBNET'}
    ip = testphpipam.get_ip_interface_by_subnet_name('non-existent ip')
    assert ip is None


def test_get_ipnetwork_by_subnet_name(testphpipam):
    ip = testphpipam.get_ipnetwork_by_subnet_name('non-existent ip')
    assert ip is None


def test_get_ip_interface_list_by_subnet_name(testphpipam):
    iplist = testphpipam.get_ip_interface_list_by_subnet_name('TEST%')
    assert iplist == [{'description': u'test ip #1',
                       'dnsname': u'test-ip-1',
                       'ip': ip_interface('10.1.0.1/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #2',
                       'dnsname': u'test-ip-2',
                       'ip': ip_interface('10.1.0.2/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #3',
                       'dnsname': u'test-ip-3',
                       'ip': ip_interface('10.1.0.3/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #4',
                       'dnsname': u'test-ip-4',
                       'ip': ip_interface('10.1.0.7/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #5',
                       'dnsname': u'test-ip-5',
                       'ip': ip_interface('10.1.0.8/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #6',
                       'dnsname': u'test-ip-6',
                       'ip': ip_interface('10.1.0.9/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #7',
                       'dnsname': u'test-ip-7',
                       'ip': ip_interface('10.1.0.10/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip group 1',
                       'dnsname': u'test-ip-8',
                       'ip': ip_interface('10.2.0.1/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip group 1',
                       'dnsname': u'test-ip-9',
                       'ip': ip_interface('10.2.0.2/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #10',
                       'dnsname': u'test-ip-10',
                       'ip': ip_interface('10.2.0.3/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #11',
                       'dnsname': u'test-ip-11',
                       'ip': ip_interface('10.2.0.4/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #12',
                       'dnsname': u'test-ip-12',
                       'ip': ip_interface('10.2.0.5/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #13',
                       'dnsname': u'test-ip-13',
                       'ip': ip_interface('10.2.0.6/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #15',
                       'dnsname': u'test-ip-15',
                       'ip': ip_interface('10.5.0.0/31'),
                       'subnet_name': u'TEST /31 SUBNET GROUP'},
                      ]


def test_get_ipnetwork_list_by_subnet_name(testphpipam):
    iplist = testphpipam.get_ipnetwork_list_by_subnet_name('TEST%')
    assert iplist == [{'description': u'test ip #1',
                       'dnsname': u'test-ip-1',
                       'ip': ip_interface('10.1.0.1/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #2',
                       'dnsname': u'test-ip-2',
                       'ip': ip_interface('10.1.0.2/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #3',
                       'dnsname': u'test-ip-3',
                       'ip': ip_interface('10.1.0.3/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #4',
                       'dnsname': u'test-ip-4',
                       'ip': ip_interface('10.1.0.7/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #5',
                       'dnsname': u'test-ip-5',
                       'ip': ip_interface('10.1.0.8/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #6',
                       'dnsname': u'test-ip-6',
                       'ip': ip_interface('10.1.0.9/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip #7',
                       'dnsname': u'test-ip-7',
                       'ip': ip_interface('10.1.0.10/28'),
                       'subnet_name': u'TEST /28 SUBNET'},
                      {'description': u'test ip group 1',
                       'dnsname': u'test-ip-8',
                       'ip': ip_interface('10.2.0.1/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip group 1',
                       'dnsname': u'test-ip-9',
                       'ip': ip_interface('10.2.0.2/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #10',
                       'dnsname': u'test-ip-10',
                       'ip': ip_interface('10.2.0.3/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #11',
                       'dnsname': u'test-ip-11',
                       'ip': ip_interface('10.2.0.4/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #12',
                       'dnsname': u'test-ip-12',
                       'ip': ip_interface('10.2.0.5/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #13',
                       'dnsname': u'test-ip-13',
                       'ip': ip_interface('10.2.0.6/29'),
                       'subnet_name': u'TEST FULL /29 SUBNET'},
                      {'description': u'test ip #15',
                       'dnsname': u'test-ip-15',
                       'ip': ip_interface('10.5.0.0/31'),
                       'subnet_name': u'TEST /31 SUBNET GROUP'},
                      ]


def test_get_subnet_by_desc(testphpipam):
    assert testphpipam.get_subnet_by_desc('unknown subnet') is None
    subnet = testphpipam.get_subnet_by_desc('TEST /28 SUBNET')
    assert subnet['subnet'] == ip_network('10.1.0.0/28')
    assert subnet['description'] == 'TEST /28 SUBNET'
    subnet = testphpipam.get_subnet_by_desc('TEST /31 SUBNET GROUP')
    assert subnet['subnet'] == ip_network('10.4.0.0/31')
    assert subnet['description'] == 'TEST /31 SUBNET GROUP'


def test_get_subnet_list_by_desc(testphpipam):
    assert testphpipam.get_subnet_list_by_desc('unknown subnet') == []
    subnetlist = testphpipam.get_subnet_list_by_desc('TEST /28 SUBNET')
    assert subnetlist == [{'subnet': ip_network('10.1.0.0/28'),
                           'description': 'TEST /28 SUBNET'}]
    subnetlist = testphpipam.get_subnet_list_by_desc('TEST /31 SUBNET GROUP')
    assert subnetlist == [{'subnet': ip_network('10.4.0.0/31'),
                           'description': 'TEST /31 SUBNET GROUP'},
                          {'subnet': ip_network('10.5.0.0/31'),
                           'description': 'TEST /31 SUBNET GROUP'}]


def test_get_num_ips_by_desc(testphpipam):
    assert testphpipam.get_num_ips_by_desc('unknown ip') == 0
    assert testphpipam.get_num_ips_by_desc('test ip #2') == 1
    assert testphpipam.get_num_ips_by_desc('test ip group 1') == 2


def test_get_num_subnets_by_desc(testphpipam):
    assert testphpipam.get_num_subnets_by_desc('unknown subnet') == 0
    assert testphpipam.get_num_subnets_by_desc('TEST /28 SUBNET') == 1
    assert testphpipam.get_num_subnets_by_desc('TEST /31 SUBNET GROUP') == 2


def test_get_hostname_by_ip(testphpipam):
    assert testphpipam.get_hostname_by_ip(
        ip_address('1.1.1.1')) is None
    assert testphpipam.get_hostname_by_ip(
        ip_address('10.2.0.2')) == 'test-ip-9'


def test_get_description_by_ip(testphpipam):
    assert testphpipam.get_description_by_ip(
        ip_address('1.1.1.1')) is None
    assert testphpipam.get_description_by_ip(
        ip_address('10.2.0.2')) == 'test ip group 1'
