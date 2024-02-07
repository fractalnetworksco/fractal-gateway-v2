# resolve gateway1 and gateway2 to localhost for local testing
hosts-setup:
	grep -q gateway1 /etc/hosts || echo "127.0.0.1 gateway1" | sudo tee -a /etc/hosts ;
	grep -q gateway2 /etc/hosts || echo "127.0.0.1 gateway2" | sudo tee -a /etc/hosts ;
