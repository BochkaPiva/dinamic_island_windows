# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
class NoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        response['X-Frame-Options'] = 'DENY'
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response
