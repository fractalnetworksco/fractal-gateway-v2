.PHONY: hosts-setup

# resolve gateway1 and gateway2 to localhost for local testing
hosts-setup:
	grep -q gateway1.com /etc/hosts || echo "127.0.0.1 gateway1.com" | sudo tee -a /etc/hosts ;
	grep -q gateway2.com /etc/hosts || echo "127.0.0.1 gateway2.com" | sudo tee -a /etc/hosts ;
	grep -q matrix.gateway1.com /etc/hosts || echo "127.0.0.1 matrix.gateway1.com" | sudo tee -a /etc/hosts ;
	grep -q matrix.gateway2.com /etc/hosts || echo "127.0.0.1 matrix.gateway2.com" | sudo tee -a /etc/hosts ;
