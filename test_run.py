import importlib
m = importlib.import_module('rastreador_ofertas')
print('produto_eh_bloqueado("Incubadora X") ->', m.produto_eh_bloqueado('Incubadora X'))
print('produto_eh_bloqueado("Smartphone") ->', m.produto_eh_bloqueado('Smartphone'))
print('gerar_chamada_inteligente(None,None) ->', m.gerar_chamada_inteligente(None, None))
print('gerar_chamada_inteligente("Fone de ouvido",59.9,"AUDIO") ->', m.gerar_chamada_inteligente('Fone de ouvido', 59.9, 'AUDIO'))
