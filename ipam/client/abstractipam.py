#!/usr/bin/env python

from abc import ABCMeta, abstractmethod


class AbstractIPAM:
    __metaclass__ = ABCMeta

    @abstractmethod
    def add_ip(self, ipaddr, dnsname, description):
        raise NotImplementedError()

    @abstractmethod
    def add_next_ip(self, subnet, dnsname, description):
        raise NotImplementedError()

    @abstractmethod
    def get_next_free_ip(self, subnet):
        raise NotImplementedError()

    @abstractmethod
    def add_top_level_subnet(self, subnet, description):
        raise NotImplementedError()

    @abstractmethod
    def add_next_subnet(self, parent_subnet, prefixlen, description):
        raise NotImplementedError()

    @abstractmethod
    def delete_subnet(self, subnet, empty_subnet):
        raise NotImplementedError()

    @abstractmethod
    def get_hostname_by_ip(self, ip):
        raise NotImplementedError()

    @abstractmethod
    def get_description_by_ip(self, ip):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_interface_list_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_interface_list_by_subnet_name(self, subnet_name):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_interface_by_subnet_name(self, subnet_name):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_interface_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_list_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_ip_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_subnet_list_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_subnet_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_subnet_with_ips(self, subnet):
        raise NotImplementedError()

    @abstractmethod
    def get_num_ips_by_desc(self, description):
        raise NotImplementedError()

    @abstractmethod
    def get_num_subnets_by_desc(self, description):
        raise NotImplementedError()
