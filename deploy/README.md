# Publicar Atlas + CTI num servidor

Esta distribuição inclui o backend Python, o mapa e projetos persistentes. Não é
um site estático: GitHub Pages e um Worker de assets não executam este backend.
Esta configuração destina-se a uma instância privada com acesso partilhado; não
implementa contas separadas nem isola projetos por utilizador.

## Requisitos

- Servidor Linux com Docker Engine e Docker Compose, disponível continuamente.
- Domínio ou subdomínio com DNS apontado ao servidor, portas TCP 80/443 abertas.
- Saída HTTPS para os fornecedores descritos no README e DNS/TCP 80/443 para os
  alvos pesquisados. As quotas e licenças das fontes continuam a aplicar-se.

O servidor e o domínio podem ter custos. Não é criada nenhuma subscrição por
estes ficheiros. A aplicação existente em workers.dev não é substituída.

## Arranque

1. Clona o repositório no servidor e entra na pasta OSINT.
2. Executa `cp deploy/environment.example .env` e `chmod 600 .env`.
3. Gera um hash com `docker run --rm -it caddy:2-alpine caddy hash-password`.
   Introduz a palavra-passe no pedido interativo; não a passes na linha de comandos.
4. Edita `.env`: domínio, utilizador e hash bcrypt entre aspas simples. Não coloques
   a palavra-passe em texto simples nem publiques o ficheiro.
5. Executa `docker compose up -d --build` e `docker compose ps`.
6. Abre `https://TEU-DOMINIO`, autentica-te e verifica Atlas, `/cti/`, criação de
   projeto e uma consulta real. O Caddy obtém e renova o certificado TLS.

O backend não publica a porta 8000 no servidor. O gateway protege também as APIs
e os recursos estáticos. O estado SQLite fica no volume `atlas_data`, separado da
imagem. Mantém apenas uma instância da aplicação por volume.

## Verificação e manutenção

- Sem credenciais, `curl -I https://TEU-DOMINIO/` deve devolver **401**.
- `curl --user TEU-UTILIZADOR https://TEU-DOMINIO/health` pede a palavra-passe e
  deve devolver `status: ok`. Testa também os feeds: uma falha do fornecedor não
  deve ser confundida com ausência de indicadores.
- Atualiza com `git pull --ff-only` e `docker compose up -d --build`.
- Consulta falhas com `docker compose logs --tail=100`. Não publiques os logs
  sem os rever.
- Para parar sem apagar projetos: `docker compose down`. **Não uses `down -v`**:
  remove os volumes, incluindo projetos e certificados.
- Para backup consistente, para primeiro o backend com `docker compose stop atlas`,
  copia `/data` com `docker compose cp atlas:/data ./backup-atlas` e volta a arrancar
  com `docker compose start atlas`. Guarda o backup num local privado e testa o
  restauro antes de depender dele. Não o adiciones ao Git.

Um proxy DNS Cloudflare pode ser usado com TLS Full (strict). Confirma primeiro
que o certificado do servidor é válido. Não desatives a verificação TLS.
