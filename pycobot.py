#!/usr/bin/python
# -*- coding: utf-8 -*-

import irc.client
from irc import events
import sys, json, logging, re, time
from pprint import pprint
# Variables globales:
conf = {} # Configuración
servers = {} # Servidores

client = None

_rfc_1459_command_regexp = re.compile("^(:(?P<prefix>[^ ]+) +)?(?P<command>[^ ]+)( *(?P<argument> .+))?")
class pyCoBot:
    def __init__(self, server, client, conf):
        self.handlers = []
        self.server = client.server()
        self.server.connect(server, conf['port'], conf['nick'],
            username = conf['nick'], ircname = "pyCoBot")
        self.server.add_global_handler("all_raw_messages", self.allraw)
        servers[server] = conf
        servers[server]['servobj'] = server  
        self.modules = {}
        self.commandhandlers = {}
        self.conf = conf
        
        for i, val in enumerate(conf['modules']):
            self.loadmod(conf['modules'][i], conf['server'], self)
        
    
    def allraw(self, con, event):
        ev = self.processline(event.arguments[0], con) 
        for i, val in enumerate(self.handlers): # TODO: hacer esto es feo, cambiarlo por algo mejor!
            if ev.type == self.handlers[i]['numeric']:
                getattr(self.handlers[i]['mod'], self.handlers[i]['func'])(self.server)
        
        if ev.type == "privmsg" or ev.type == "pubmsg":
            p = re.compile("(?:"+re.escape(self.conf['prefix'])+"|"+re.escape(self.conf['nick'])+"[:, ]? )(.*)(?!\w+)")
            m = p.search(ev.arguments[0])
            if not m == None:
                com = m.group(1)
                try:
                    self.commandhandlers[com]
                except NameError:
                    return 0
                getattr(self.commandhandlers[com]['mod'], self.commandhandlers[com]['func'])(self.server, ev)
        if ev.type == "welcome":
            for i, val in enumerate(servers[event.realserv]['autojoin']):
                con.join(servers[event.realserv]['autojoin'][i])

    # Procesa una linea y retorna un Event
    def processline(self, line, c):
        prefix = None
        command = None
        arguments = None

        m = _rfc_1459_command_regexp.match(line)
        if m.group("prefix"):
            prefix = m.group("prefix")

        if m.group("command"):
            command = m.group("command").lower()

        if m.group("argument"):
            a = m.group("argument").split(" :", 1)
            arguments = a[0].split()
            if len(a) == 2:
                arguments.append(a[1])

        # Translate numerics into more readable strings.
        command = events.numeric.get(command, command)

        if command in ["privmsg", "notice"]:
            target, message = arguments[0], arguments[1]
            messages = irc.client._ctcp_dequote(message)

            if command == "privmsg":
                if irc.client.is_channel(target):
                    command = "pubmsg"
            else:
                if irc.client.is_channel(target):
                    command = "pubnotice"
                else:
                    command = "privnotice"

            for m in messages:
                if isinstance(m, tuple):
                    if command in ["privmsg", "pubmsg"]:
                        command = "ctcp"
                    else:
                        command = "ctcpreply"

                    if command == "ctcp" and m[0] == "ACTION":
                        return irc.client.Event("action", prefix, target, m[1:])
                    else:
                        return irc.client.Event(command, irc.client.NickMask(prefix), target, m)
                else:
                    return irc.client.Event(command, irc.client.NickMask(prefix), target, [m])
        else:
            target = None

            if command == "quit":
                arguments = [arguments[0]]
            elif command == "ping":
                target = arguments[0]
            else:
                target = arguments[0]
                arguments = arguments[1:]

            if command == "mode":
                if not is_channel(target):
                    command = "umode"

            return irc.client.Event(command, prefix, target, arguments)
        

    def addHandler(self, numeric, modulo, func):
        """ Registra un handler con el bot.
        Parametros:
            - server: Nombre (dirección) del servidor en el que se registra el handler (la misma
            que aparece en la configuración)
            - numeric: Nombre del comando IRC que accionara el handler (lista: irc/events.py)
            - modulo: 'self' del módulo en el que se registra el handler
            - func: la función que se llamará en el módulo en cuestión
        """
        h = {}
        h['numeric'] = numeric
        h['mod'] = modulo
        h['func'] = func

        self.handlers.append(h)
        logging.debug("Registrado handler en '%s' ('%s')" % (self.conf['server'], numeric))
        
        
    def addCommandHandler(self, command, module, func):
        """ Registra un commandHandler con el bot (un comando, bah)
        Parametros:
            - server: Nombre (dirección) del servidor en el que se registra el handler (la misma
            que aparece en la configuración)
            - command: Nombre del comando que se va a registrar
            - módulo: 'self' del módulo donde se registra el handler
            - fund; la función que se llamara en el módulo en cuestión.
        Los comandos se accionan al escribir <prefijo>comando; <nickdelbot>, comando;
        <nickdelbot>: comando y <nickdelbot> comando """
        h = {}
        h['mod'] = module
        h['func'] = func
        self.commandhandlers[command] = h
        logging.debug("Registrado commandHandler en '%s' ('%s')" % (self.conf['server'], command))
        
    # carga de modulos
    def loadmod(self, module, cli, bot):
        logging.info('Cargando modulo "%s" en %s' % (module, self.conf['server']))
        try:
            # D:
            modulef = open('modules/%s/%s.py' % (module, module)).read()
            nclassname = "m" + str(int(time.time())) + "x" + module
            mod = re.sub(r".*class (.*):", "class " + nclassname + ":", modulef)
            open('tmp/%s.py' % module, 'w').write(mod)

            self.modules[module] = my_import("tmp."+module+"."+nclassname)(bot, cli)

        except IOError:
            logging.error("No se pudo cargar el modulo '%s'. No se ha encontrado el archivo." % module)

# :P
def isset(variable):
	return variable in locals() or variable in globals()

def main():
    logging.basicConfig(level=logging.DEBUG)
    
    try:
        jsonConf = open("pycobot.conf").read()
    except IOError:
        logging.error('No se ha podido abrir el archivo de configuración')
        sys.exit("Missing config file!")

    conf = json.loads(jsonConf) # Cargar la configuración
    
    client= irc.client.IRC()
    
    # Añadir servidores
    for i, val in enumerate(conf['irc']):
        pycobot = pyCoBot(conf['irc'][i]['server'], client, conf['irc'][i])        
        
    client.process_forever()

def my_import(cl):
        d = cl.rfind(".")
        classname = cl[d+1:len(cl)]
        m = __import__(cl[0:d], globals(), locals(), [classname])
        return getattr(m, classname)
if __name__ == "__main__":
    main()
