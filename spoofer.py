import uuid
import subprocess
import random
import winreg
import wmi
import ctypes
import sys
from ctypes import windll

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class SystemSpoofer:
    def __init__(self):
        if not is_admin():
            print("Este programa precisa ser executado como administrador!")
            sys.exit(1)
        
    def spoof_hwid(self):
        try:
            new_hwid = str(uuid.uuid4())
            key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
            registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, 
                                        winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(registry_key, "HwProfileGuid", 0, 
                            winreg.REG_SZ, f"{{{new_hwid}}}")
            winreg.CloseKey(registry_key)
            return new_hwid
        except Exception as e:
            return f"Erro ao alterar HWID: {str(e)}"

    def spoof_mac(self, adapter_name="Ethernet"):
        try:
            new_mac = self.generate_random_mac()
            new_mac_formatted = new_mac.replace(":", "")
            
            key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
            registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 
                                        0, winreg.KEY_ALL_ACCESS)
            
            # Procura o adaptador correto
            for i in range(0, 999):
                try:
                    subkey_name = f"{key_path}\\{i:04d}"
                    subkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_name, 
                                          0, winreg.KEY_ALL_ACCESS)
                    
                    adapter_desc = winreg.QueryValueEx(subkey, "DriverDesc")[0]
                    if adapter_name.lower() in adapter_desc.lower():
                        # Define o novo MAC
                        winreg.SetValueEx(subkey, "NetworkAddress", 0, 
                                        winreg.REG_SZ, new_mac_formatted)
                        winreg.CloseKey(subkey)
                        
                        # Reinicia o adaptador
                        subprocess.run(["netsh", "interface", "set", "interface", 
                                    adapter_name, "disable"], capture_output=True)
                        subprocess.run(["netsh", "interface", "set", "interface", 
                                    adapter_name, "enable"], capture_output=True)
                        return new_mac
                except WindowsError:
                    continue
            return "Adaptador não encontrado"
        except Exception as e:
            return f"Erro ao alterar MAC: {str(e)}"

    def spoof_guid(self):
        try:
            new_guid = str(uuid.uuid4())
            key_path = r"SOFTWARE\Microsoft\Cryptography"
            registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 
                                        0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(registry_key, "MachineGuid", 0, 
                            winreg.REG_SZ, new_guid)
            winreg.CloseKey(registry_key)
            return new_guid
        except Exception as e:
            return f"Erro ao alterar GUID: {str(e)}"

    @staticmethod
    def generate_random_mac():
        mac = [random.randint(0x00, 0xff) for _ in range(6)]
        mac[0] = (mac[0] & 0xfe) | 0x02  # Garante MAC unicast e locally administered
        return ':'.join(map(lambda x: f"{x:02x}", mac))

def main():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return

    spoofer = SystemSpoofer()
    
    while True:
        print("\n=== System ID Spoofer ===")
        print("1. Alterar HWID")
        print("2. Alterar MAC")
        print("3. Alterar GUID")
        print("4. Alterar Todos")
        print("5. Sair")
        
        choice = input("\nEscolha uma opção: ")
        
        if choice == "1":
            new_hwid = spoofer.spoof_hwid()
            print(f"Novo HWID: {new_hwid}")
        
        elif choice == "2":
            adapter = input("Nome do adaptador (padrão: Ethernet): ") or "Ethernet"
            new_mac = spoofer.spoof_mac(adapter)
            print(f"Novo MAC: {new_mac}")
        
        elif choice == "3":
            new_guid = spoofer.spoof_guid()
            print(f"Novo GUID: {new_guid}")
        
        elif choice == "4":
            print("\nAlterando todos os IDs...")
            new_hwid = spoofer.spoof_hwid()
            new_mac = spoofer.spoof_mac()
            new_guid = spoofer.spoof_guid()
            print(f"Novo HWID: {new_hwid}")
            print(f"Novo MAC: {new_mac}")
            print(f"Novo GUID: {new_guid}")
        
        elif choice == "5":
            break
        
        else:
            print("Opção inválida!")
        
        input("\nPressione Enter para continuar...")

if __name__ == "__main__":
    main()