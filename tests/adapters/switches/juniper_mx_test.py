# Copyright 2018 Internap.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import textwrap
import unittest

from flexmock import flexmock, flexmock_teardown
from hamcrest import assert_that, equal_to, instance_of, contains_string, has_length
from ncclient.operations import RPCError
from ncclient.xml_ import to_ele

from netman.adapters.switches.juniper.base import Juniper
from netman.adapters.switches.juniper.mx import netconf
from netman.core.objects.exceptions import VlanAlreadyExist, BadVlanNumber, BadVlanName, UnknownVlan, UnknownInterface
from netman.core.objects.port_modes import ACCESS
from netman.core.objects.switch_descriptor import SwitchDescriptor
from netman.core.switch_factory import RealSwitchFactory
from tests.adapters.switches.juniper_test import an_ok_response, is_xml, a_configuration, an_rpc_response


def test_factory():
    switch = RealSwitchFactory().get_switch_by_descriptor(
                SwitchDescriptor(hostname='hostname', model='juniper_mx', username='username', password='password', port=22)
            )

    assert_that(switch, instance_of(Juniper))
    assert_that(switch.switch_descriptor.hostname, equal_to("hostname"))
    assert_that(switch.switch_descriptor.model, equal_to("juniper_mx"))
    assert_that(switch.switch_descriptor.username, equal_to("username"))
    assert_that(switch.switch_descriptor.password, equal_to("password"))
    assert_that(switch.switch_descriptor.port, equal_to(22))


class JuniperMXTest(unittest.TestCase):
    def setUp(self):
        self.switch = netconf(SwitchDescriptor(model='juniper_mx', hostname="toto"))

        self.netconf_mock = flexmock()
        self.switch.netconf = self.netconf_mock
        self.switch.in_transaction = True

    def tearDown(self):
        flexmock_teardown()

    def test_add_vlan(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>PATATE</name>
                <vlan-id>900</vlan-id>
              </domain>
            </bridge-domains>
        """))

        self.netconf_mock.should_receive("edit_config").once().with_args(target="candidate", config=is_xml("""
            <config>
              <configuration>
                <bridge-domains>
                  <domain>
                    <name>VLAN1000</name>
                    <vlan-id>1000</vlan-id>
                    <description>Shizzle</description>
                  </domain>
                </bridge-domains>
              </configuration>
            </config>
        """)).and_return(an_ok_response())

        self.switch.add_vlan(1000, name="Shizzle")

    def test_add_vlan_already_in_use_raises(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>PATATE</name>
                <vlan-id>1000</vlan-id>
              </domain>
            </bridge-domains>
        """))

        self.netconf_mock.should_receive("edit_config").never()

        with self.assertRaises(VlanAlreadyExist) as expect:
            self.switch.add_vlan(1000)

        assert_that(str(expect.exception), contains_string("Vlan 1000 already exist"))

    def test_add_existing_vlan_raises(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>VLAN1000</name>
                <vlan-id>1000</vlan-id>
              </domain>
            </bridge-domains>
        """))

        self.netconf_mock.should_receive("edit_config").never()

        with self.assertRaises(VlanAlreadyExist) as expect:
            self.switch.add_vlan(1000)

        assert_that(str(expect.exception), contains_string("Vlan 1000 already exist"))

    def test_add_vlan_bad_vlan_id(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
                <filter>
                  <configuration>
                    <bridge-domains />
                  </configuration>
                </filter>
            """)).and_return(a_configuration(""))

        self.netconf_mock.should_receive("edit_config").once().with_args(target="candidate", config=is_xml("""
                <config>
                  <configuration>
                    <bridge-domains>
                      <domain>
                        <name>VLAN9000</name>
                        <vlan-id>9000</vlan-id>
                      </domain>
                    </bridge-domains>
                  </configuration>
                </config>
            """)).and_raise(RPCError(to_ele(textwrap.dedent("""
                <rpc-error xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" xmlns:junos="http://xml.juniper.net/junos/15.1R4/junos" xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">>
                <error-severity>error</error-severity>
                <error-info>
                  <bad-element>domain</bad-element>
                </error-info>
                <error-message>Value 9000 is not within range (1..4094)</error-message>
                </rpc-error>
            """))))

        with self.assertRaises(BadVlanNumber) as expect:
            self.switch.add_vlan(9000)

        assert_that(str(expect.exception), equal_to("Vlan number is invalid"))

    def test_add_vlan_empty_vlan_name(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
                <filter>
                  <configuration>
                    <bridge-domains />
                  </configuration>
                </filter>
            """)).and_return(a_configuration(""))

        self.netconf_mock.should_receive("edit_config").once().with_args(target="candidate", config=is_xml("""
                <config>
                  <configuration>
                    <bridge-domains>
                      <domain>
                        <name>VLAN1000</name>
                        <vlan-id>1000</vlan-id>
                        <description></description>
                      </domain>
                    </bridge-domains>
                  </configuration>
                </config>
            """)).and_raise(RPCError(to_ele(textwrap.dedent("""
                 <rpc-error xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
                 xmlns:junos="http://xml.juniper.net/junos/15.1R4/junos"
                 xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <error-type>protocol</error-type>
                    <error-tag>operation-failed</error-tag>
                    <error-severity>error</error-severity>
                    <error-message>description: '': Must be a string of 255 characters or less</error-message>
                    <error-info>
                      <bad-element>domain</bad-element>
                    </error-info>
                  </rpc-error>
            """))))

        with self.assertRaises(BadVlanName) as expect:
            self.switch.add_vlan(1000, "")

        assert_that(str(expect.exception), equal_to("Vlan name is invalid"))

    def test_add_vlan_too_long_vlan_name(self):
        longString = 'a' * 256
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
                <filter>
                  <configuration>
                    <bridge-domains />
                  </configuration>
                </filter>
            """)).and_return(a_configuration(""))

        self.netconf_mock.should_receive("edit_config").once().with_args(target="candidate", config=is_xml("""
                <config>
                  <configuration>
                    <bridge-domains>
                      <domain>
                        <name>VLAN1000</name>
                        <vlan-id>1000</vlan-id>
                        <description>{}</description>
                      </domain>
                    </bridge-domains>
                  </configuration>
                </config>
            """.format(longString))).and_raise(RPCError(to_ele(textwrap.dedent("""
                 <rpc-error xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
                 xmlns:junos="http://xml.juniper.net/junos/15.1R4/junos"
                 xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <error-type>protocol</error-type>
                    <error-tag>operation-failed</error-tag>
                    <error-severity>error</error-severity>
                    <error-message>description: '{}': Must be a string of 255 characters or less</error-message>
                    <error-info>
                      <bad-element>domain</bad-element>
                    </error-info>
                  </rpc-error>
            """.format(longString)))))

        with self.assertRaises(BadVlanName) as expect:
            self.switch.add_vlan(1000, longString)

        assert_that(str(expect.exception), equal_to("Vlan name is invalid"))

    def test_remove_vlan_ignores_removing_interface_not_created(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <bridge-domains />
                <interfaces />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>STANDARD</name>
                <vlan-id>10</vlan-id>
              </domain>
            </bridge-domains>
        """))

        self.netconf_mock.should_receive("edit_config").once().with_args(target="candidate", config=is_xml("""
            <config>
              <configuration>
                <bridge-domains>
                  <domain operation="delete">
                    <name>STANDARD</name>
                  </domain>
                </bridge-domains>
              </configuration>
            </config>
        """)).and_return(an_ok_response())

        self.switch.remove_vlan(10)

    def test_remove_vlan_invalid_vlan_raises(self):
        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <bridge-domains />
                <interfaces />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>ANOTHER</name>
                <vlan-id>10</vlan-id>
              </domain>
            </bridge-domains>
        """))

        with self.assertRaises(UnknownVlan) as expect:
            self.switch.remove_vlan(20)

        assert_that(str(expect.exception), equal_to("Vlan 20 not found"))

    def test_get_interface(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
            <filter>
              <configuration>
                <interfaces>
                    <interface>
                        <name>xe-0/0/1</name>
                    </interface>
                </interfaces>
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <interfaces>
              <interface>
                <name>xe-0/0/1</name>
                <unit>
                  <name>0</name>
                  <family>
                    <bridge>
                    </bridge>
                  </family>
                </unit>
              </interface>
            </interfaces>
            <bridge-domains/>
        """))

        interface = self.switch.get_interface('xe-0/0/1')

        assert_that(interface.name, equal_to("xe-0/0/1"))
        assert_that(interface.shutdown, equal_to(False))
        assert_that(interface.port_mode, equal_to(ACCESS))
        assert_that(interface.access_vlan, equal_to(None))
        assert_that(interface.trunk_native_vlan, equal_to(None))
        assert_that(interface.trunk_vlans, equal_to([]))
        assert_that(interface.auto_negotiation, equal_to(None))
        assert_that(interface.mtu, equal_to(None))

    def test_get_interfaces_supports_named_vlans(self):
        self.switch.in_transaction = True

        self.netconf_mock.should_receive("rpc").with_args(is_xml("""
                    <get-interface-information>
                      <terse/>
                    </get-interface-information>
                """)).and_return(an_rpc_response(textwrap.dedent("""
                    <interface-information style="terse">
                      <physical-interface>
                        <name>
                          xe-0/0/1
                        </name>
                        <admin-status>
                          up
                        </admin-status>
                        <oper-status>
                          down
                        </oper-status>
                        <logical-interface>
                          <name>
                            xe-0/0/1.0
                          </name>
                          <admin-status>
                            up
                          </admin-status>
                          <oper-status>
                            down
                          </oper-status>
                          <filter-information></filter-information>
                          <address-family>
                            <address-family-name>
                              eth-switch
                            </address-family-name>
                          </address-family>
                        </logical-interface>
                      </physical-interface>
                    </interface-information>
                """)))

        self.netconf_mock.should_receive("get_config").with_args(source="candidate", filter=is_xml("""
            <filter>
              <configuration>
                <interfaces />
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <bridge-domains>
              <domain>
                <name>MON_VLAN_PREFERE</name>
                <vlan-id>1234</vlan-id>
                <description>Oh yeah</description>
              </domain>
            </bridge-domains>
            <interfaces>
              <interface>
                <name>xe-0/0/1</name>
                <unit>
                  <name>0</name>
                  <family>
                    <bridge>
                        <vlan-id-list>1234</vlan-id-list>
                    </bridge>
                  </family>
                </unit>
              </interface>
            </interfaces>
        """))
        if1, = self.switch.get_interfaces()

        assert_that(if1.name, equal_to("xe-0/0/1"))
        assert_that(if1.access_vlan, equal_to(1234))

    def test_get_interfaces_lists_configuration_less_interfaces(self):
        self.switch.in_transaction = False

        self.netconf_mock.should_receive("rpc").with_args(is_xml("""
                    <get-interface-information>
                      <terse/>
                    </get-interface-information>
                """)).and_return(an_rpc_response(textwrap.dedent("""
                    <interface-information style="terse">
                      <physical-interface>
                        <name>
                    xe-0/0/1
                    </name>
                        <admin-status>
                    up
                    </admin-status>
                        <oper-status>
                    down
                    </oper-status>
                      </physical-interface>
                      <physical-interface>
                        <name>
                    xe-0/0/2
                    </name>
                        <admin-status>
                    down
                    </admin-status>
                        <oper-status>
                    down
                    </oper-status>
                      </physical-interface>
                    </interface-information>
                """)))

        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
            <filter>
              <configuration>
                <interfaces />
                <bridge-domains />
              </configuration>
            </filter>
        """)).and_return(a_configuration("""
            <interfaces />
            <bridge-domains/>
        """))

        if1, if2 = self.switch.get_interfaces()

        assert_that(if1.name, equal_to("xe-0/0/1"))
        assert_that(if1.shutdown, equal_to(False))
        assert_that(if1.port_mode, equal_to(ACCESS))
        assert_that(if1.access_vlan, equal_to(None))
        assert_that(if1.trunk_native_vlan, equal_to(None))
        assert_that(if1.trunk_vlans, equal_to([]))

        assert_that(if2.name, equal_to("xe-0/0/2"))
        assert_that(if2.shutdown, equal_to(True))

    def test_get_vlan_interfaces(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
                <filter>
                  <configuration>
                    <bridge-domains>
                      <domain>
                        <vlan-id>705</vlan-id>
                      </domain>
                    </bridge-domains>
                    <interfaces />
                  </configuration>
                </filter>
            """)).and_return(a_configuration("""
                <bridge-domains>
                  <domain>
                    <name>VLAN705</name>
                    <vlan-id>705</vlan-id>
                  </domain>
                </bridge-domains>
                <interfaces>
                  <interface>
                    <name>xe-0/0/6</name>
                    <unit>
                      <family>
                        <bridge>
                          <vlan-id-list>687</vlan-id-list>
                          <vlan-id-list>705</vlan-id-list>
                          <vlan-id-list>708</vlan-id-list>
                        </bridge>
                      </family>
                    </unit>
                  </interface>
                  <interface>
                    <name>xe-0/0/7</name>
                    <unit>
                      <family>
                        <bridge>
                          <vlan-id-list>705</vlan-id-list>
                        </bridge>
                      </family>
                    </unit>
                  </interface>
                  <interface>
                    <name>xe-0/0/8</name>
                    <unit>
                      <family>
                        <bridge>
                          <vlan-id-list>456</vlan-id-list>
                        </bridge>
                      </family>
                    </unit>
                  </interface>
                  <interface>
                    <name>xe-0/0/9</name>
                    <unit>
                      <family>
                        <bridge>
                          <vlan-id-list>700-800</vlan-id-list>
                        </bridge>
                      </family>
                    </unit>
                  </interface>
                </interfaces>
            """))

        vlan_interfaces = self.switch.get_vlan_interfaces(705)

        assert_that(vlan_interfaces, equal_to(["xe-0/0/6", "xe-0/0/7", "xe-0/0/9"]))

    def test_get_nonexistent_interface_raises(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
                    <filter>
                      <configuration>
                          <interfaces>
                            <interface>
                              <name>xe-0/0/INEXISTENT</name>
                            </interface>
                          </interfaces>
                        <bridge-domains/>
                      </configuration>
                    </filter>
                """)).and_return(a_configuration("""
                    <interfaces/>
                    <bridge-domains/>
                """))
        self.netconf_mock.should_receive("rpc").with_args(is_xml("""
                    <get-interface-information>
                      <terse/>
                    </get-interface-information>
                """)).and_return(an_rpc_response(textwrap.dedent("""
                    <interface-information style="terse">
                      <physical-interface>
                        <name>
                          xe-0/0/1
                        </name>
                        <admin-status>
                          down
                        </admin-status>
                        <oper-status>
                          down
                        </oper-status>
                      </physical-interface>
                    </interface-information>
                """)))

        with self.assertRaises(UnknownInterface) as expect:
            self.switch.get_interface('xe-0/0/INEXISTENT')

        assert_that(str(expect.exception), equal_to("Unknown interface xe-0/0/INEXISTENT"))

    def test_get_unconfigured_interface_could_be_disabled(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
                        <filter>
                          <configuration>
                              <interfaces>
                                <interface>
                                  <name>xe-0/0/27</name>
                                </interface>
                              </interfaces>
                            <bridge-domains/>
                          </configuration>
                        </filter>
                    """)).and_return(a_configuration("""
                        <interfaces/>
                        <bridge-domains/>
                    """))
        self.netconf_mock.should_receive("rpc").with_args(is_xml("""
                        <get-interface-information>
                          <terse/>
                        </get-interface-information>
                    """)).and_return(an_rpc_response(textwrap.dedent("""
                        <interface-information style="terse">
                          <physical-interface>
                            <name>
                              xe-0/0/27
                            </name>
                            <admin-status>
                              down
                            </admin-status>
                            <oper-status>
                              down
                            </oper-status>
                          </physical-interface>
                        </interface-information>
                    """)))

        assert_that(self.switch.get_interface('xe-0/0/27').shutdown, equal_to(True))

    def test_get_vlan_interfaces_nonexisting_vlan(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
                    <filter>
                      <configuration>
                        <bridge-domains>
                          <domain>
                            <vlan-id>9999999</vlan-id>
                          </domain>
                        </bridge-domains>
                        <interfaces />
                      </configuration>
                    </filter>
                """)).and_return(a_configuration("""
                    <vlans />
                    <interfaces>
                        <interface>
                          <name>xe-0/0/9</name>
                          <unit>
                            <family>
                              <bridge>
                                  <vlan-id-list>705</vlan-id-list>
                              </bridge>
                            </family>
                          </unit>
                        </interface>
                    </interfaces>
                """))
        with self.assertRaises(UnknownVlan):
            self.switch.get_vlan_interfaces("9999999")

    def test_get_vlan_interfaces_with_name_as_member(self):
        self.switch.in_transaction = False
        self.netconf_mock.should_receive("get_config").with_args(source="running", filter=is_xml("""
                        <filter>
                          <configuration>
                            <bridge-domains>
                              <domain>
                                <vlan-id>705</vlan-id>
                              </domain>
                            </bridge-domains>
                            <interfaces />
                          </configuration>
                        </filter>
                    """)).and_return(a_configuration("""
                        <bridge-domains>
                          <domain>
                            <name>bleu</name>
                            <vlan-id>705</vlan-id>
                          </domain>
                        </bridge-domains>
                        <interfaces>
                            <interface>
                              <name>xe-0/0/9</name>
                              <unit>
                                <family>
                                  <bridge>
                                    <vlan-id-list>bleu</vlan-id-list>
                                  </bridge>
                                </family>
                              </unit>
                            </interface>
                        </interfaces>
                    """))

        vlan_interfaces = self.switch.get_vlan_interfaces(705)

        assert_that(vlan_interfaces, equal_to(["xe-0/0/9"]))
