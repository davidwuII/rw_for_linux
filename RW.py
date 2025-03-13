import os
import mmap
import struct
import time
import sys
import select

# ANSI escape codes for displaying red text
RED_COLOR = "\033[31m"
YELLOW_COLOR = "\033[93m"
RESET_COLOR = "\033[0m"  # Reset color to default

def list_pcie_devices():
    pci_devices_path = "/sys/bus/pci/devices"
    devices = os.listdir(pci_devices_path)
    device_list = []
    
    print("Available PCIe Devices:")
    for idx, device in enumerate(devices):
        device_path = os.path.join(pci_devices_path, device)
        vendor_file = os.path.join(device_path, "vendor")
        device_file = os.path.join(device_path, "device")
        
        # Check if the device has valid vendor and device ID files
        if os.path.exists(vendor_file) and os.path.exists(device_file):
            with open(vendor_file, "r") as vf, open(device_file, "r") as df:
                vendor_id = vf.read().strip()
                device_id = df.read().strip()
                print(f"[{idx}] PCI Device: {device}, Vendor ID: {vendor_id}, Device ID: {device_id}")
                device_list.append(device)
    
    return device_list

def list_pcie_bars(device):
    bar_list = []
    for bar_num in range(6):  # BARs typically range from 0 to 5
        resource_path = f"/sys/bus/pci/devices/{device}/resource{bar_num}"
        if os.path.exists(resource_path):
            bar_list.append(bar_num)
    return bar_list

def write_pcie_register(mm, offset, value):
    # Write to the memory-mapped region at the specified offset
    reg_offset = offset
    mm.seek(reg_offset)
    mm.write(struct.pack("<I", value))  # Little-endian packing of 32-bit integer
    print(f"Written 0x{value:08X} to offset 0x{offset:04X}")

def read_pcie_bar(device, bar_num, offset_input):
    resource_path = f"/sys/bus/pci/devices/{device}/resource{bar_num}"
    if not os.path.exists(resource_path):
        print(f"BAR{bar_num} resource file not found.")
        return
    
    # Handle the '0x0' case by ensuring it is interpreted as 0
    if offset_input.lower() == "0x0" or offset_input == "0":
        offset = 0
    else:
        # Remove leading zeros from offset input, allowing for inputs like "0xD0" or "D0"
        clean_offset_input = offset_input.lower().lstrip('0x').lstrip('0')  # Strip leading '0x' and leading zeros
        if clean_offset_input == "":  # Handle the case where the input is "0" or just "0x0"
            offset = 0
        else:
            offset = int(clean_offset_input, 16)  # Convert cleaned offset to decimal

    row_size = 16   # 16 rows
    col_size = 4    # 4 Registers per row
    reg_size = 4    # 4 bytes per register (32-bit)
    
    with open(resource_path, "r+b") as f:
        file_size = os.path.getsize(resource_path)
        mapping_size = max(file_size, 4 * mmap.PAGESIZE)  # Set mapping size to at least 4MB
        mm = mmap.mmap(f.fileno(), mapping_size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)  # Allow writing
        
        print(f"Reading BAR{bar_num} Registers starting from offset {hex(offset)}. Press 'q' to quit or 'w' to write.")
        
        while True:
            print("\033[H\033[J", end="")  # Clear screen
            print(f"Press 'q' to quit or 'w' to write (with 'Enter').")
            print(f"BAR{bar_num} Registers starting from offset {hex(offset)}:")
            for row in range(row_size):
                row_offset = offset + (row * col_size * reg_size)
                row_values = []
                for col in range(col_size):
                    reg_offset = row_offset + (col * reg_size)
                    mm.seek(reg_offset)
                    data = mm.read(reg_size)
                    value = struct.unpack("<I", data)[0]  # Little-endian unpacking of 32-bit integer
                    color = YELLOW_COLOR if value != 0 else ""
                    row_values.append(f"{color}0x{value:08X}{RESET_COLOR}")
                
                # Add color to offset part
                print(f"{RED_COLOR}0x{row_offset:04X}{RESET_COLOR}:  " + "  ".join(row_values))
            
            time.sleep(0.1)  # 100ms refresh interval
            
            # Check if keyboard input is available
            if is_input_available():
                user_input = sys.stdin.read(1).strip().lower()
                if user_input == 'q':
                    break
                elif user_input == 'w':
                    # Stop refreshing and allow the user to input a new register and value to write
                    print("\nWriting mode enabled. Please enter the offset and value to write.")
                    write_offset_input = input("Enter the offset (e.g., 0x7000): ").strip()
                    
                    # Validate the offset input
                    clean_write_offset_input = write_offset_input.lower().lstrip('0x').lstrip('0')
                    if clean_write_offset_input == "":  # Handle the case where the input is "0" or just "0x0"
                        write_offset = 0
                    elif clean_write_offset_input and all(c in "0123456789abcdef" for c in clean_write_offset_input):
                        write_offset = int(clean_write_offset_input, 16)
                        write_value_input = input("Enter the value to write (e.g., 0x12345678): ").strip()
                        
                        # Validate the value input
                        clean_write_value_input = write_value_input.lower().lstrip('0x').lstrip('0')
                        if clean_write_value_input and all(c in "0123456789abcdef" for c in clean_write_value_input):
                            write_value = int(clean_write_value_input, 16)
                            # Perform the write operation
                            write_pcie_register(mm, write_offset, write_value)
                        else:
                            print("Invalid value format. Please enter a valid 8-digit hexadecimal value (e.g., 0x12345678).")
                    else:
                        print("Invalid offset format. Please enter a valid hexadecimal value.")
        
        mm.close()

def is_input_available():
    # Check if there's keyboard input available without blocking
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    return bool(rlist)

if __name__ == "__main__":
    devices = list_pcie_devices()
    if not devices:
        print("No PCIe devices found.")
    else:
        try:
            choice = int(input("Select a device by number: "))
            if 0 <= choice < len(devices):
                device = devices[choice]
                available_bars = list_pcie_bars(device)
                if not available_bars:
                    print("No available BARs found.")
                else:
                    print("Available BARs:", available_bars)
                    bar_choice = int(input("Select BAR: "))
                    if bar_choice in available_bars:
                        offset_input = input("Enter the offset (e.g., 0x7000): ").strip()
                        
                        # Ensure the user input is a valid hexadecimal value
                        clean_offset_input = offset_input.lower().lstrip('0x').lstrip('0')
                        if clean_offset_input == "":  # Handle the case where the input is "0" or just "0x0"
                            offset = 0
                            try:
                                # Convert offset to decimal and start reading the registers
                                read_pcie_bar(devices[choice], bar_choice, offset_input)
                            except ValueError:
                                print("Invalid offset. Please enter a valid hexadecimal value.")
                        elif clean_offset_input and all(c in "0123456789abcdef" for c in clean_offset_input):
                            offset = int(clean_offset_input, 16)
                            try:
                                # Convert offset to decimal and start reading the registers
                                read_pcie_bar(devices[choice], bar_choice, offset_input)
                            except ValueError:
                                print("Invalid offset. Please enter a valid hexadecimal value.")
                        else:
                            print("Invalid offset format. Please enter a valid hexadecimal value.")
                    else:
                        print("Invalid BAR selection.")
            else:
                print("Invalid device selection.")
        except ValueError:
            print("Invalid input. Please enter a number.")
