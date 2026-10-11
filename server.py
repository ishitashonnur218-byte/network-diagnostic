import socket

HOST="0.0.0.0"
PORT=5005

server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
server.bind((HOST,PORT))

print(f"UDP server listening on {PORT}")

while True:
	data, client_addr=server.recvfrom(1024)
	print(f"Recieved: {data.decode()} from {client_addr}")
	server.sendto(data,client_addr)
