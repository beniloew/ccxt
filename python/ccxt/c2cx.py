from ccxt.base.exchange import Exchange
import hashlib
from ccxt.base.errors import ExchangeError
import json
from ccxt.base.errors import AuthenticationError
from ccxt.base.errors import InsufficientFunds
from ccxt.base.errors import InvalidOrder
from ccxt.base.errors import OrderNotFound
from ccxt.base.errors import InvalidNonce


class c2cx (Exchange):

    def describe(self):
        return self.deep_extend(super(c2cx, self).describe(), {
            'id': 'c2cx',
            'name': 'C2CX',
            'countries': 'CN',
            'rateLimit': 3000,
            'has': {
                # 'CORS': False,
                # 'fetchOpenOrders': True,
            },
            'urls': {
                'api': 'https://api.c2cx.com/v1',
                'www': 'https://www.c2cx.com',
                'fees': 'https://www.c2cx.com/in/fees',
            },
            'api': {
                'public': {
                    'get': [
                        'getorderbook',
                    ],
                },
                'private': {
                    'post': [
                        'getbalance',
                        'createorder',
                        'getorderinfo',
                        'cancelorder',
                    ],
                    'get': [
                    ],
                },
            },
            'markets': {
                'SKY/BTC': {'id': 'BTC_SKY', 'symbol': 'SKY/BTC', 'base': 'SKY', 'quote': 'BTC'},
            },
            'fees': {
                'trading': {
                    'maker': 0.2 / 100,
                    'taker': 0.2 / 100,
                },
            },
            'limits': {
                'amount': {
                    'min': 1,
                    'max': 1000000000,
                }
            },
            'precision': {
                'amount': 2,
                'price': 5,
            },
            'exceptions': {
                'messages': {
                    'Sign is wrong': AuthenticationError,
                    # 'Nonce is too small': InvalidNonce,
                    # 'Order not found': OrderNotFound,
                    'symbol not exists': ExchangeError,
                    # 'user': {
                    #     'not_enough_free_balance': InsufficientFunds,
                    # },
                    # 'price': {
                    #     'must_be_positive': InvalidOrder,
                    # },
                    # 'quantity': {
                    #     'less_than_order_size': InvalidOrder,
                    # },
                },
            },
        })

    def fetch_order_book(self, symbol, limit=None, params={}):
        orderbook = self.publicGetGetorderbook(self.extend({
            'symbol': self.market_id(symbol),
        }, params))
        # print orderbook
        return self.parse_order_book(orderbook['data'], int(orderbook['data']['timestamp']) * 1000)

    def create_order(self, symbol, type, side, amount, price=None, params={}):
        if type != 'limit':
            raise ExchangeError(self.id + ' only limit orders are implemented(though market can be done)')

        order = {
            'priceTypeId': type,
            'symbol': self.market_id(symbol),
            'orderType': side,
            'quantity': amount,
            'isAdvancedOrder': '0',
        }

        if type == 'limit':
            order['price'] = price

        response = self.privatePostCreateorder(self.extend(order, params))
        try:
            data = response['data']
        except:
            raise ExchangeError(self.id + ' Create order failed. response: {}'.format(response))
        id = self.safe_string(data, 'orderId')
        timestamp = self.milliseconds()
        amount = float(amount)
        price = float(price)
        status = 'open'
        order = {
            'id': id,
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'lastTradeTimestamp': None,
            'status': status,
            'symbol': symbol,
            'type': type,
            'side': side,
            'price': price,
            'cost': price * amount,
            'amount': amount,
            'remaining': amount,
            'filled': 0.0,
            'fee': None,
            'trades': None,
        }
        return self.extend({'info': response}, order)

    def cancel_order(self, id, symbol=None, params={}):
        response = self.privatePostCancelorder(self.extend({
            'orderid': id,
        }, params))
        try:
            if response['code'] != 200 or response['message'] != 'Success':
                raise ExchangeError(self.id + ' Cancel order failed. Order id: {}, response: {}'.format(id, response))
        except:
            raise ExchangeError(self.id + ' Cancel order failed. Order id: {}, response: {}'.format(id, response))
        return response

    def fetch_order(self, id, symbol=None, params={}):
        order = self.privatePostGetorderinfo(self.extend({
            'orderid': id,
            'symbol' : self.market_id(symbol),
        }, params))

        statusCodeToStatus = {1: 'open', #''pending',
                              2: 'open',
                              3: 'open', #''partial',
                              4: 'closed',
                              5: 'canceled',
                              6: 'closed', # Error
                              7: 'open', # Suspended(insufficient funds)
                              #8,TriggerPending
                              #9,StopLossPending
                              11: 'closed',
                              12: 'open' # cancelling
                             }

        data = order['data']
        timestamp = data['createDate']
        amount = data['amount']
        filled = float(data['completedAmount'])
        return {
            'id': str(data['orderId']),
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'lastTradeTimestamp': None,
            'type': None, # not suppplied in order info
            'status': statusCodeToStatus[data['status']],
            'symbol': symbol,
            'side': data['type'],
            'price': data['price'],
            'amount': amount,
            'filled': filled,
            'remaining': amount - filled,
            'trades': None,
            'fee': None, # Not provided
            'info': order,
        }

    def fetch_balance(self, params={}):
        balances = self.privatePostGetbalance(params)
        result = {'info': balances}
        print balances
        data = balances['data']
        frozen = data['frozen']
        free = data['balance']
        for cur in free:
            if cur == 'total':
                continue
            free_cur = float(free[cur])
            frozen_cur = float(frozen[cur])
            result[cur] = {'free' : free_cur,
                           'used' : frozen_cur,
                           'total' : free_cur + frozen_cur}
        return self.parse_balance(result)

    def sign(self, path, api='public', method='GET', params={}, headers=None, body=None):
        # print("path: {}, api: {}, method: {}, params: {}, headers: {}, body: {}".format(path, api, method, params, headers, body))
        url = self.urls['api'] + '/' + path
        if api == 'public':
            if params:
                url += '?' + self.urlencode(params)
        elif method == 'POST':
            self.check_required_credentials()
            body = 'apiKey={}&'.format(self.apiKey)
            for p in sorted(params):
                body += '{}={}&'.format(p, params[p])
            signStr = body + 'secretKey={}'.format(self.secret)
            # print('signStr: {}'.format(signStr))
            sign = self.hash(signStr).upper()
            body += 'sign={}'.format(sign)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        # print 'url: {}, body: {}'.format(url, body)
        return {'url': url, 'method': method, 'body': body, 'headers': headers}

    def handle_errors(self, code, reason, url, method, headers, body):
        # print('handle err. code:{}, reason:{}, body:{}, url: {}'.format(code, reason, body, url))
        if len(body) > 0:
            if body[0] == '{':
                response = json.loads(body)
                if 'code' in response:
                    code = self.safe_string(response, 'code')
                    if code == '200':
                        return
                    msg = self.safe_string(response, 'message')
                    messages = self.exceptions['messages']
                    print "msg is: {}".format(msg)
                    feedback = self.id + ' ' + body
                    if msg in messages:
                        raise messages[msg](feedback)
                    else:
                        raise ExchangeError(feedback)
                raise ExchangeError(self.id + ': "error" in response: ' + body)