import requests
import urllib.parse
from config import OP_BASE_URL, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI

class OpenProjectAPI:
    def __init__(self, base_url):
        self.base_url = base_url
    
    def get_authorization_url(self, client_id, redirect_uri):
        """دریافت URL برای احراز هویت"""
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'api_v3 bcf_v2_1'
        }
        return f"{self.base_url}/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    def get_token_with_code(self, code, client_id, client_secret, redirect_uri):
        """دریافت توکن با authorization code"""
        token_url = f"{self.base_url}/oauth/token"
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(token_url, data=data, headers=headers, verify=False)
        return response
    
    def get_user_info(self, access_token):
        """دریافت اطلاعات کاربر"""
        url = f"{self.base_url}/api/v3/users/me"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        return response

# ایجاد نمونه API
op_api = OpenProjectAPI(OP_BASE_URL)
