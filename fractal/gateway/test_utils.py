import sh

from .utils import generate_wireguard_keypair


def test_generate_wireguard_keypair():
    for _ in range(50):
        private_key, public_key = generate_wireguard_keypair()
        assert len(private_key) == 44
        assert len(public_key) == 44
        assert sh.wg("pubkey", _in=private_key).strip() == public_key
