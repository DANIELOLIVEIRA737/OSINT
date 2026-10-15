# Atlas — OSINT público

Aplicação web em português para investigar informação pública sobre domínios, sites e endereços IP. Python 3.12 ou superior, sem dependências externas ou chaves de API.

## Executar

```sh
cd /workspace/OSINT
python3 app.py
```

O servidor escuta na porta 8000 (`PORT` permite alterá-la). O endpoint `/health` verifica o serviço. A interface está em `/`.

## Funcionalidades

- DNS A, AAAA, MX, NS, TXT e CAA através do Google Public DNS.
- Título, cabeçalhos HTTP e até 100 ligações da página indicada (sem rastreio recursivo).
- Certificado TLS validado: titular, emissor, validade e nomes.
- IP, localização aproximada, operador e ASN através de ipwho.is.
- Exportação JSON com fontes, data UTC e falhas por consulta.

A aplicação não persiste pesquisas. Os fornecedores DNS/IP recebem as consultas; os sites recebem o pedido HTTP. A localização é da rede, não de uma pessoa. Falhas de rede, limites dos fornecedores e certificados inválidos são apresentados por fonte. Não existe suite de testes externa nem etapa de compilação.

## Rede e utilização

São necessários HTTPS para `dns.google` e `ipwho.is`, DNS do sistema e ligações de saída para as portas 80/443 dos sites consultados. A inspeção HTTP/TLS usa ligações diretas com IP validado para impedir acesso a redes privadas e DNS rebinding. Ambientes que só permitem saída por proxy podem bloquear esta parte; a aplicação mostra a falha sem inventar resultados. Não desativa a verificação TLS.

O servidor destina-se a um ambiente de desenvolvimento de confiança. Antes de o expor publicamente, adicionar autenticação e limites por utilizador num reverse proxy. As pesquisas são limitadas a quatro em simultâneo. Não realiza port scanning, exploração ou consultas autenticadas.

## Testes

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```
