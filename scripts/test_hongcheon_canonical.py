import unittest
from support_runtime.boards import canonical

class PublicMenu(unittest.TestCase):
    def test_public_menu(self):
        for page in ('List','View'):
            u=f'https://www.hongcheon.go.kr/www/selectBbsNtt{page}.do?bbsNo=140&key=1709&nttNo=146188'
            self.assertIsNotNone(canonical(u,'www.hongcheon.go.kr'))

    def test_credentials_still_blocked(self):
        u='https://www.hongcheon.go.kr/www/selectBbsNttView.do?bbsNo=140&key=1709&nttNo=146188'
        for bad in (u.replace('1709','1710'),u.replace('140','141'),u+'&key=1709',u+'&key=',u+'&token=secret',u+'&token=',u.replace('/www/','/other/'),u.replace('www.hongcheon.go.kr','example.org')):
            self.assertIsNone(canonical(bad,'example.org' if 'example.org' in bad else 'www.hongcheon.go.kr'))

if __name__=='__main__':unittest.main()
