# Publicar no Render

[Criar a partir do Blueprint](https://render.com/deploy?repo=https://github.com/DANIELOLIVEIRA737/OSINT)

1. Entra na tua conta Render e abre o link acima. Se necessário, autoriza o
   acesso ao repositório `DANIELOLIVEIRA737/OSINT`, branch `main`.
2. O Render lê `render.yaml`. Confirma o serviço **atlas-cti**, região Frankfurt,
   plano **Starter** e disco persistente de **1 GB**. **São recursos pagos**;
   confirma o valor apresentado no painel antes de criar o serviço.
3. Preenche `ATLAS_PASSWORD` com uma palavra-passe única de pelo menos 16
   caracteres. Este campo é secreto no Render e não é guardado no GitHub.
   O utilizador inicial é `atlas`; podes mudar `ATLAS_ADMIN` no painel.
4. Cria o Blueprint e acompanha o primeiro deploy. Abre o endereço HTTPS
   `onrender.com` indicado pelo Render quando o serviço estiver disponível.
5. Autentica-te e verifica a página inicial, `/cti/`, criação de projetos e uma
   pesquisa. O Render termina HTTPS; não precisas do Caddy nem do Compose.

Só `GET /health` é público, para o healthcheck, sem projetos ou dados de pesquisa.
As páginas, recursos estáticos e APIs exigem autenticação. É um workspace privado
partilhado, sem contas/projetos separados por utilizador. Usa sempre HTTPS.

O disco é montado em `/data`; SQLite fica em `/data/atlas/atlas.sqlite3`. O arranque
prepara as permissões da pasta e passa para UID/GID 10001 antes de executar Atlas.
Mantém uma única instância por disco. Não removas o disco ao atualizar a aplicação.
Monitorizações funcionam enquanto o serviço está ativo. Mantém backups privados;
exportar um projeto na GUI não exporta toda a base de dados nem os agendamentos.

Valida a persistência criando um projeto, reiniciando o serviço no painel e
confirmando que o projeto continua disponível. Testa feeds reais: as verificações
locais usam fixtures e não provam disponibilidade nem quotas dos fornecedores no
Render. A consulta HTTP/TLS aos alvos precisa de saída de rede permitida.

Se o arranque falhar com `ATLAS_PASSWORD`, define o segredo no painel e volta a
fazer deploy. Não coloques segredos no YAML nem nos logs. Para um domínio próprio,
usa a opção Custom Domains do Render e segue as instruções DNS do painel.

Não uses o plano gratuito com armazenamento efémero para este Blueprint: perderias
os projetos e agendamentos. Rever o Blueprint e criar o serviço na tua conta é o
passo de publicação; adicionar estes ficheiros ao GitHub não cria alojamento.
