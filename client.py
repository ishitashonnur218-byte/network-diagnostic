import socket
import time

SERVER_IP="10.0.0.2"
PORT=5005
TOTAL_PROBES=20
TIMEOUT=1.0

client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
client.settimeout(TIMEOUT)

recieved=0
rtt_values=[]

print(f"Testing {SERVER_IP}:{PORT}")
print(f"Sending {TOTAL_PROBES} UDP probes\n")

for seq in range(1,TOTAL_PROBES+1):
	message=f"probes--{seq}".encode()
	start=time.perf_counter()

	try:
		client.sendto(message,(SERVER_IP,PORT))
		responce,_=client.recvfrom(1024)

		if responce!=message:
			print(f"Probe {seq}: Invalid responce")
			continue
		rtt=(time.perf_counter()-start)*1000
		recieved+=1
		rtt_values.append(rtt)

		print(f"Probe {seq}: Reply recieved, RTT={rtt:.2f} ms")
	except socket.timeout:
		print(f"Probe {seq}: Request timed out")
	time.sleep(0.2)
client.close()

lost=TOTAL_PROBES - recieved
loss_perc=(lost/TOTAL_PROBES)*100

print("\n----Diagnostic Summary----")
print(f"Packets sent: 	{TOTAL_PROBES}")
print(f"Packets recieved: {recieved}")
print(f"Packets lost: {lost}")
print(f"Packet loss%: {loss_perc}")

if rtt_values:
	print(f"Average RTT: {sum(rtt_values)/len(rtt_values):.2f} ms")
	print(f"Minimum RTT: {min(rtt_values):.2f} ms")
	print(f"Maximum RTT: {max(rtt_values):.2f} ms")
