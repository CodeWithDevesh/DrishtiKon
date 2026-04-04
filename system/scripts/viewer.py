import cv2
import socket
import struct
import pickle

def main():
    host_ip = '127.0.0.1' 
    port = 9999

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    print(f"[*] Attempting to connect to video feed at {host_ip}:{port}...")
    try:
        client_socket.connect((host_ip, port))
        print("[+] Connected! Press 'q' on your keyboard to close the viewer.")
    except Exception as e:
        print(f"[-] Could not connect to the server: {e}")
        print("    Make sure run_face.py is currently running!")
        return

    data = b""
    payload_size = struct.calcsize("Q") 

    try:
        while True:
            while len(data) < payload_size:
                packet = client_socket.recv(4 * 1024) # Read in 4KB chunks
                if not packet: break
                data += packet
            
            if not data:
                break

            # Extract the packed message size
            packed_msg_size = data[:payload_size]
            data = data[payload_size:]
            msg_size = struct.unpack("Q", packed_msg_size)[0]

            # Retrieve all the frame data based on that message size
            while len(data) < msg_size:
                data += client_socket.recv(4 * 1024)

            frame_data = data[:msg_size]
            data = data[msg_size:]

            # Unpickle the data back into a readable OpenCV image frame
            frame = pickle.loads(frame_data)
            
            # Display the frame on your monitor
            cv2.imshow("Robotics Pipeline - Live Feed", frame)

            # Press 'q' to quit the viewer gracefully
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except Exception as e:
        print(f"[-] Stream ended or encountered an error: {e}")
    finally:
        client_socket.close()
        cv2.destroyAllWindows()
        print("[-] Viewer shut down.")

if __name__ == "__main__":
    main()