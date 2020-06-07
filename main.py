import config
import aiosqlite
from aiosqlite import Error
import asyncio
from aiohttp import web
import xml.etree.ElementTree as ET
import urllib
import os
from time import strftime, gmtime
import base64
import re
import code_builder
from io import BytesIO


class Template(object):

    def __init__(self, text, *contexts):
        self.context = {}
        for context in contexts:
            self.context.update(context)
        self.varsSet = set()
        self.loopvarsSet = set()
        code = code_builder.CodeBuilder()
        code.add_line("def render_function(context, do_dots):")
        code.indent()
        vcode = code.add_section()
        code.add_line("result = []")
        code.add_line("append_result = result.append")
        code.add_line("extend_result = result.extend")
        arr = []
        def createoutput():
            if len(arr) == 1:
                code.add_line("append_result(%s)" % arr[0])
            elif len(arr) > 1:
                code.add_line("extend_result([%s])" % ", ".join(arr))
            del arr[:]
        opersStack = []
        tknList = re.split(r"(?s)({{.*?}}|{%.*?%}|{\]}|{\[})",text)
        for tkn in tknList:
            tkn = re.sub(r"\s*\n\s*", "", tkn.strip())
            if tkn.startswith('{'):
                sidx, eidx = 2, -2
                if tkn.startswith('{%'):
                    createoutput()
                    words = tkn[sidx:eidx].strip().split()
                    if words[0] == 'if':
                        opersStack.append('if')
                        str = "if "
                        for word in words[1:]:
                            if word in context or word in self.loopvarsSet:
                                str += "%s " % self._exprssion_manger(word)
                            else:
                                str += word + " "
                        code.add_line(str)
                        code.indent()
                    elif words[0] == 'else':
                        opersStack.append('else')
                        code.add_line("else :" )
                        code.indent()
                    elif words[0] == 'elif':
                        opersStack.append('elif')
                        str = "elif "
                        for word in words[1:]:
                            if word in context or word in self.loopvarsSet:
                                str += "%s " % self._exprssion_manger(word)
                            else:
                                str += word + " "
                        code.add_line(str)
                        code.indent()
                    elif words[0] == 'while':
                        opersStack.append('while')
                        str = "while "
                        for word in words[1:]:
                            if word in context or word in self.loopvarsSet:
                                str += "%s " % self._exprssion_manger(word)
                            else:
                                str += word + " "
                        code.add_line(str)
                        code.indent()
                    elif words[0] == 'for':
                        opersStack.append('for')
                        self._addvar(words[1], self.loopvarsSet)
                        var =""
                        var+=words[3]
                        if var.endswith(":"):
                            var=(var)[:-1]
                        code.add_line("for c_%s in %s:" % (words[1], self._exprssion_manger(var)))
                        code.indent()
                    else:
                        continue
                elif tkn.startswith('{{'):
                    expression = self._exprssion_manger(tkn[sidx:eidx].strip())
                    arr.append("str(%s)" % expression)
                elif tkn.startswith('{[}'):
                    print("")
                elif tkn.startswith('{]}'):
                    code.dedent()
            else:
                if tkn:
                    arr.append(repr(tkn))
            createoutput()
        for nameOfvar in self.varsSet - self.loopvarsSet:
            vcode.add_line("c_%s = context[%r]" % (nameOfvar, nameOfvar))
        code.add_line('return "".join(result)')
        code.dedent()
        self._render_function = code.get_globals()['render_function']

    def _exprssion_manger(self, expr):
        if "." in expr:
            expr_dots = expr.split(".")
            code = self._exprssion_manger(expr_dots[0])
            expr_args = ", ".join(repr(d) for d in expr_dots[1:])
            code = "do_dots(%s, %s)" % (code, expr_args)
        elif "|" in expr:
            expr_pipes = expr.split("|")
            code = self._exprssion_manger(expr_pipes[0])
            for f in expr_pipes[1:]:
                self._addvar(f, self.varsSet)
                code = "c_%s(%s)" % (f, code)

        else:
            self._addvar(expr, self.varsSet)
            code = "c_%s" % expr
        return code

    def _addvar(self, name, vars_set):
        vars_set.add(name)

    def render(self, context=None):
        cntxt_ren = dict(self.context)
        if context:
            cntxt_ren.update(context)
        return self._render_function(cntxt_ren, self._do_dots)

    def _do_dots(self, value, *dots):
        for dot in dots:
            value = getattr(value, dot)
            if callable(value):
                value = value()
        return value


#config file
baseDir = config.server_prop['base_dir']
port = config.server_prop['port']
time_out = config.server_prop['timeout']

def getmimedict():
    tree = ET.parse('mime.xml')
    root = tree.getroot()
    mimeDict = {}
    for elem in root:
        mimeDict[elem[0].text] = elem[1].text
    return mimeDict


async def create_connection(db_file):
    conn = None
    try:
        conn = await aiosqlite.connect(db_file)
    except Error as e:
        print(e)
    return conn


#xml file:mime
mimeDict = getmimedict()

#database file:user_auth and connect
database = r".\user_auth.db"

async def getrowinrealmdatabase(path):
    conn = await aiosqlite.connect(database)
    await conn.execute('INSERT INTO Realms VALUES ("Realm1", "/Technion")')
    await conn.commit()
    cursor = await conn.execute("SELECT * FROM Realms WHERE rootdir=?",(path,))
    row = await cursor.fetchall()
    return row


async def getprotectedrow(path):
    path_dirs = str(path).split('/')[1:]
    curr_dir = ""
    row = []
    for dir in path_dirs:
        if(dir != "/"):
        # check if it's in realm
            curr_dir += "/" + dir
            row = await getrowinrealmdatabase(curr_dir)
            if (len(row) > 0):
                return row
    return row


async def isprotected(path):
    row = await getprotectedrow(path)
    if len(row) > 0:
        return True, (row[0])[0]
    return False, ''


async def getrowinuserdatabse(username,password):
    conn = await aiosqlite.connect(database)
    await conn.execute('INSERT INTO Users VALUES ("Aseel", "Sakas", "Realm1")')
    await conn.commit()
    cursor = await conn.execute("SELECT realm FROM Users WHERE username=? AND password=?", (username,password))
    row = await cursor.fetchall()
    return row


async def checkcredintials(username,password,path):
    protected_row = await getprotectedrow(path)
    user_row = await getrowinuserdatabse(username,password)
    if (protected_row[0])[0] == (user_row[0])[0]:
        return True
    return False


async def file_listing_page(path):
    html_code = '<!DOCTYPE html>'
    html_code += '<html>'
    html_code += '<head><title>Index</title></head>'
    html_code += '<body>'
    html_code += '<ul>'
    pdir = path[:path.rfind('/')]
    if pdir == '' or pdir == '/':
        pdir = '/.'
    html_code += '<li><a href="'+pdir+'">[parent directory]</a></li>' # self load if root
    path = urllib.parse.unquote(path)
    full_path = baseDir + path
    files = os.listdir(full_path[0:])
    for name in files:
        name = urllib.parse.unquote(name)
        link = path + "/" + name
        link = urllib.parse.quote(link)
        html_code += '<li><a href="' + link + '">' + name + '</a></li>'
    html_code += '</ul>'
    html_code += '</body>'
    html_code += '</html>'
    return html_code


async def getparams(path):
    dict_params = {}
    path = urllib.parse.unquote(str(path))
    params_str = (str(path).split('?'))[1]
    params = params_str.split('&')
    for param in params:
        key = param.split('=')[0]
        value = param.split('=')[1]
        if(value[0] == '['):
            value_list = []
            values_in_array = (value[1:-1]).split(",")
            for v in values_in_array:
                if v.startswith('"'):
                    v = v.strip("\"")
                    value_list.append(v)
                else:
                    if "." in v:
                        value_list.append(float(v))
                    else:
                        value_list.append(int(v))
            dict_params[key] = value_list
        elif (value[0] == '{'):
            value_dict = {}
            values_in_array = (value[1:-1]).split(",")
            dict_keys_in_array = []
            dict_values_in_array = []
            for val in values_in_array:
                dict_keys_in_array.append(val.split(":")[0])
                dict_values_in_array.append(val.split(":")[1])
            count = 0
            for dict_key in dict_keys_in_array:
                value_dict[dict_key] = dict_values_in_array[count]
                count+=1
            dict_params[key] = value_dict
        else:
            value = value.strip("\"")
            dict_params[key] = value
    return dict_params


async def handler(request):
    text = ''
    curr_date = strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())
    headers = {}
    headers['Date'] = curr_date
    headers['charset'] = "utf-8"
    headers['Connection'] = "close"
    headers['Content-Type'] = "text/html"
    headers['Cache-Control'] = 'must-revalidate'

    if request.method != 'GET':
        body2 = text.encode('utf-8')
        return web.Response(body=body2, status=501, headers=headers)
    relative_url = request.rel_url

    #CHECKING IF THE DIRECTORY IS PROTECTED
    isprot = await isprotected(request.rel_url)
    if isprot[0]:
        #CHECKING IF THE USER INSERTED USERNAME AND PASSWORD
        #if "Authorization" in request.headers:
        if request.headers.get('Authorization') is not None:
            user_pass_encoded_with_basic = request.headers.get('Authorization')
            user_pass_encoded = (user_pass_encoded_with_basic.split())[1]
            user_pass_decoded = base64.b64decode(user_pass_encoded).decode("utf-8")
            username = user_pass_decoded.split(":")[0]
            password = user_pass_decoded.split(":")[1]
            #CHECK IF HIS USERNAME AND PASSWORD MATCH THE REALM OF THE PATH
            checkcred = await checkcredintials(username, password, relative_url)
            if not checkcred:
                #IF NOT THEN NEED TO RETURN 403
                body2 = text.encode('utf-8')
                return web.Response(body=body2, status=403, headers=headers)
        else:
            #IF THE USER HASEN'T INSERTED A USERNAME AND A PASSWORD RETURN 401
            headers['WWW-Authenticate'] = 'Basic realm="' + isprot[1] + '"'
            body2 = text.encode('utf-8')
            return web.Response(body=body2, status=401, headers=headers)

    full_path = urllib.parse.unquote(baseDir + str(relative_url))
    if relative_url != '/favicon.ico':
        path = urllib.parse.unquote(full_path)[0:]
        path_without_context = path.split("?")[0]
        if os.path.isfile(path_without_context):
            filetype = full_path.split(".")[-1]
            j_filetype = full_path.split(".")[1]
            if j_filetype[0:2] == "j2":
                dict_params = await getparams(relative_url)
                file_path = (str(relative_url).split('?'))[0]
                full_path = baseDir + file_path
                file_j = open(str(urllib.parse.unquote(full_path)[0:]), "r")
                f_text = file_j.read()
                text = Template(f_text, dict_params)
                try:
                    P = text.render(dict_params)
                except:
                    return web.Response(body=P, status=500, headers=headers)
                return web.Response(body=P, status=200, headers=headers)
            if filetype in mimeDict.keys():
                headers['Content-Type'] = mimeDict[filetype]
            else:
                headers['Content-Type'] = ''
            in_file = open(str(urllib.parse.unquote(full_path)[0:]), "rb")
            body2 = in_file.read()
            return web.Response(body=body2, status=200, headers=headers)
        else:
            if not os.path.isdir(urllib.parse.unquote(full_path)[0:]):
                body2 = text.encode('utf-8')
                return web.Response(body=body2, status=404, headers=headers)
            text = await file_listing_page(str(relative_url))
    body2 = text.encode('utf-8')
    return web.Response(body=body2, status=200, headers=headers)


async def main():
    server = web.Server(handler)
    runner = web.ServerRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', port)
    site._shutdown_timeout = time_out
    await site.start()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(main())
    loop.run_forever()