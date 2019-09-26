from abc import ABC
from enum import Enum
#from jinja2 import Template, FileSystemLoader, Environment
import os

ansible_scripts_path = "LAB_IN_A_SERVER_ANSIBLE_SCRIPTS_PATH"
par_dir = "VAGRANT_MACHINES_FOLDER_PATH"

flavour = {
  'large': {'memory': '32768', 'cpu': '8'},
  'medium': {'memory': '16384', 'cpu': '4'},
  'small': {'memory': '8192', 'cpu': '2'}
}

class Server(ABC):

  def __init__(self, name, flavour = "low", management_ip={}, interfaces=[], provision=[]):
    self.name = name
    self.interfaces = interfaces
    self.management_ip = management_ip
    self.provision = provision
    self.flavour = flavour

  def get_config(self):
    config = self.set_initialconfig()
    config = self.set_managementip(config)
    config = self.set_interfaces(config)
    config = self.provision_vm(config)
    config = self.set_endblock(config)
    return config

  def set_initialconfig(self, config, box):
    config = config + """
    srv_name = (\"%s\").to_sym
    config.vm.define srv_name do |srv|
      srv.vm.box = \"%s\"
      if Vagrant.has_plugin?("vagrant-vbguest")
        srv.vbguest.auto_update = false
      end
      srv.vm.hostname = \"%s\""""%(self.name, box, self.name)
    return config

  def set_interfaces(self, config):
    if self.management_ip:
      ifcount = 2
    else:
      ifcount = 1
    for interface in self.interfaces:
      print(interface)
      if interface['host_only']:
        config = config + """
      srv.vm.network \'private_network\', ip: \"%s\", netmask: \"%s\", nic_type: \'82540EM\'"""%(interface['ip'], interface['netmask'])
      else :
        config = config + """
      srv.vm.network \'private_network\', ip: \"%s\", netmask: \"%s\", nic_type: \'82540EM\', virtualbox__intnet: \"%s\""""%(interface['ip'], interface['netmask'], interface['name'])
      config = config + """
      srv.vm.provision :ansible do |ansible|
        ansible.playbook = \"%s\" 
        ansible.extra_vars = {
          interface_name: \"%s\",
          ip_address: \"%s\",
          netmask: \"%s\"
        }
      end
      srv.vm.provision \"shell\", inline: \"/bin/sh /tmp/config-%s.sh\""""%(os.path.join(ansible_scripts_path, "set_interface.yml"), str("ifcfg-eth"+str(ifcount)), interface['ip'], interface['netmask'], str("ifcfg-eth"+str(ifcount)))
      ifcount += 1
    return config

  def set_endblock(self, config):
    config = config + """
    end
    config.vm.provider :virtualbox do |vb|
      vb.auto_nat_dns_proxy = false
      vb.customize [\"modifyvm\", :id, \"--memory\", \"{}\", \"--cpus\", \"{}\"]
    end """.format(flavour[self.flavour]['memory'], flavour[self.flavour]['cpu'])
    return config

  def set_managementip(self, config):
    pass

  def provision_vm(self, config):
    for item in self.provision:
      if item['method'] == 'ansible':
        print(item)
        config = config + """
      srv.vm.provision :%s do |ansible|
        ansible.playbook = %s"""%(item['method'], item['path'])
        if item['variables']:
          config = config + """
        ansible.extra_vars = {"""
          for key, value in item['variables'].items():
            if isinstance(value, str):
              config = config + """
          {}: \"{}\",""".format(key, value)
            else:
              config = config + """
          {}: {},""".format(key, value) 
          config = config + """
        }"""
        config = config + """
      end"""
      else:
        param = """
      srv.vm.provision \"%s\", """%(item['method'])
        for key, value in item.items():
          if key is not 'method':
            param = param + """{}: {}, """.format(key, value)
        config = config + param[:-2]
    return config

class CENTOS(Server):

  box = "kirankn/centOS-7.5"

  def __init__(self, name, flavour, management_ip={}, interfaces=[], provision=[]):
    super().__init__(name, flavour, management_ip, interfaces, provision)

  def set_initialconfig(self):
    return super().set_initialconfig("", self.box)

  def set_managementip(self, config):
    if self.management_ip:
      config = config + """
      srv.vm.network \"public_network\", auto_config: false, bridge: \'eno1\'
      srv.vm.provision :ansible do |ansible|
        ansible.playbook = \"%s\"
        ansible.extra_vars = {
          vm_interface: \"eth1\",
          vm_gateway_ip: \"%s\",
          vm_ip: \"%s\",
          vm_netmask: \"%s\",
          vm_dns1: \"172.21.200.60\",
          vm_dns2: \"8.8.8.8\",
          vm_domain: \"englab.juniper.net jnpr.net juniper.net\",
          ntp_server: \"ntp.juniper.net\"
        }
      end
      srv.vm.provision \"shell\", path: \"%s\""""%(os.path.join(ansible_scripts_path, 'network.yml'), self.management_ip['gateway'], self.management_ip['ip'], self.management_ip['netmask'], os.path.join(ansible_scripts_path, 'scripts/set-centos-gw.sh'))
    return config


class Switch():

  def __init__(self, name, interfaces=[]):
    self.name = name
    self.re_name = str(name+"_re")
    self.pfe_name = str(name+"_pfe")
    self.interfaces = interfaces

  def setup_box(self):
    pass

  def get_config(self):
    pass

class VQFX(Switch):

  rebox = "juniper/vqfx10k-re"
  pfebox = "juniper/vqfx10k-pfe"

  def __init__(self, name, gateway, interfaces=[]):
    super().__init__(name, interfaces)
    self.gateway = gateway

  def setup_box(self,image_for="RE"):
    if image_for == "RE":
        box = self.rebox
    else:
        box = self.pfebox
    config = """config.vm.define %s do |VAR_PLACEHOLDER|
    VAR_PLACEHOLDER.ssh.insert_key = false
    VAR_PLACEHOLDER.vm.box = \'%s\'
    VAR_PLACEHOLDER.vm.boot_timeout = 600
    VAR_PLACEHOLDER.vm.synced_folder \'.\',\'/vagrant\', disabled: true
    VAR_PLACEHOLDER.vm.network \'private_network\',auto_config: false, nic_type: \'82540EM\', virtualbox__intnet: \"%s\"
    end
    """%(str(image_for.lower()+"_name"),box,str(self.name+"_internal"))
    return config.replace("VAR_PLACEHOLDER",str("switch"+image_for.lower()))

  def get_config(self):
    #define PFE block
    config = """
    re_name = (\"%s\").to_sym
    pfe_name = (\"%s\").to_sym
    """%(self.re_name,self.pfe_name)
    config = config + self.setup_box("PFE")
    # End pfe set up block and define RE hostname block
    config = config + self.setup_box("RE")
    config = config + """config.vm.define %s do |VAR_PLACEHOLDER|
    VAR_PLACEHOLDER.vm.hostname = \"%s\"
    VAR_PLACEHOLDER.vm.network \'private_network\',auto_config: false, nic_type: \'82540EM\', virtualbox__intnet: \"%s\"
    end"""%("re_name",str(self.name+"re"),str(self.name+"_reserved_bridge"))
    config = config.replace("VAR_PLACEHOLDER",str("switch"+"re"))
    # settiing up interfaces to switch
    config = config + """
    config.vm.define %s do |VAR_PLACEHOLDER|"""%("re_name")
    config = config.replace("VAR_PLACEHOLDER",str("switch"+"re"))
    # setting up physical connections
    for interface in self.interfaces:
        config = config + self.setup_internal_network(str("switch"+"re"),interface)
    # configuring logical connection 
    config = config + """
      VAR_PLACEHOLDER.vm.provision :ansible do |ansible|
        ansible.playbook = \"/{}\"
        ansible.extra_vars = {{
          vagrant_root: \"{}\",
          lab_in_a_server: "/root/lab-in-a-server",
          switch_name: \"{}\",
          interface_count: {},
          vlan_id: {},
          gateway_ip: \"{}\"
      }}
      end""".format(os.path.join(ansible_scripts_path, 'switch_interface.yml'), "%s"%os.path.join(par_dir,inputs['name']), self.re_name, len(self.interfaces), 101, self.gateway)
    config = config.replace("VAR_PLACEHOLDER",str("switch"+"re"))
    config = config + """
    end"""
    return config

  def setup_internal_network(self, var, interface):
    interface_config = """
      %s.vm.network \'private_network\', auto_config: false, nic_type: \'82540EM\',virtualbox__intnet: \"%s\""""%(var,interface)
    return interface_config

def get_common_file_contents(api_version):
  common_content = """VAGRANTFILE_API_VERSION = \"%s\"
  vagrant_root = File.dirname(__FILE__)
  Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|"""%(api_version)
  return common_content

def append_end_block():
  return """
  end
  """

def get_devices(devices):
  config = ""
  for device in devices:
    config = config + device.get_config()
  return config

def provision_groups(groups_dict, provision_playbook):
  config = """
  if !Vagrant::Util::Platform.windows?
    config.vm.provision "ansible" do |ansible|
      ansible.groups = {"""
  param = ""
  for key, value in groups_dict.items():
    param = param + """
        \"{}\" => {}, """.format(key,value)
  config = config + param[:-2]
  config = config + """
      }
      ansible.playbook = \"%s\""""%(provision_playbook)
  config = config + """
    end"""
  return config

def generate_vagrant_file(hosts,switches,groups_dict={},provision_playbook="",file_name="Vagrantfile"):
  with open(file_name, 'w') as f:
    f.write(get_common_file_contents(2))
    f.write(get_devices(switches))
    f.write(get_devices(hosts))
    if groups_dict:
      f.write(provision_groups(groups_dict, provision_playbook))
    f.write(append_end_block())

