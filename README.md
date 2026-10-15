# Atlas 02 — Intelligence Workspace

Aplicação web de OSINT em português para domínios, sites e endereços IP públicos. Dashboard responsivo, investigação por módulos, evidências com fontes e relatórios exportáveis. Python 3.12+, sem dependências de execução externas ou chaves de API.

![Interface do Atlas em computador](docs/atlas-workspace.png)

## Início rápido

1. Descarregar e extrair o ZIP do repositório, ou usar `git clone`.
2. Abrir um terminal na pasta que contém `app.py`.
3. Executar:

```sh
python app.py
```

Em Linux/macOS, usar `python3 app.py`; no Windows também é possível usar `py app.py`.
Abrir **http://localhost:8000** no navegador. Para parar, premir **Ctrl+C** no terminal.
`PORT` permite escolher outra porta. `/health` verifica o servidor.

Para atualizar uma instalação Git, parar o servidor, executar `git pull origin main` e voltar a iniciar. Quem instalou pelo ZIP deve descarregar e extrair a versão mais recente. Uma atualização forçada do navegador pode ser necessária se houver uma versão antiga da interface em cache.

## Pesquisa essencial e aprofundada

| Módulo                                             | Essencial | Aprofundada | Fonte                                              |
| -------------------------------------------------- | --------- | ----------- | -------------------------------------------------- |
| Endereços IP                                       | Sim       | Sim         | Resolução DNS do sistema                           |
| DNS: A, AAAA, CNAME, MX, NS, TXT, CAA, SOA e DMARC | Domínios  | Domínios    | Google Public DNS                                  |
| HTTP, título, metadados, scripts e ligações        | Sites     | Sites       | Página indicada                                    |
| Indicadores de segurança e tecnologias observadas  | Sites     | Sites       | Cabeçalhos e HTML                                  |
| Certificado TLS validado                           | Sites     | Sites       | Ligação TLS ao alvo                                |
| Operador, ASN e localização aproximada             | Sim       | Sim         | ipwho.is, primeiro IP resolvido                    |
| Registo do domínio ou bloco IP                     | —         | Sim         | Bootstrap IANA + serviço RDAP oficial              |
| DNS reverso                                        | —         | Sim         | Sistema, até quatro IPs                            |
| Nomes em certificados públicos                     | —         | Domínios    | crt.sh, até 200 nomes apresentados                 |
| Páginas históricas                                 | —         | Domínios    | Internet Archive, amostra de até 40 URLs           |
| Documentos públicos                                | —         | Sites       | robots.txt, sitemap.xml e .well-known/security.txt |

Uma pesquisa aprofundada consulta até **10 módulos para domínios/sites**; os indicadores de segurança integram o módulo web. Para um IP sem URL são quatro módulos: resolução, operador, RDAP e DNS reverso. A aplicação não tenta percorrer subdomínios nem páginas históricas. Os três documentos públicos são consultados apenas no mesmo site, sem seguir os caminhos descobertos.

## Relatórios e interface

- Dashboard com cobertura dos módulos, IPs, nomes em certificados e pontos a rever.
- Filtros por infraestrutura, web/TLS e rasto digital; pesquisa textual nas evidências.
- Tecnologias acompanhadas da evidência observada, sem pressupor versões ou vulnerabilidades.
- Notas sobre HTTPS, cabeçalhos, SPF/DMARC e certificados próximos da expiração.
- Histórico dos últimos 12 relatórios apenas na memória da página. Desaparece ao atualizar/fechar.
- Exportação JSON com fontes, data UTC, duração, resultados e falhas por módulo.
- Impressão / guardar em PDF através do navegador, incluindo os módulos e secções recolhidas.
- Interface local sem fontes tipográficas ou bibliotecas carregadas de terceiros.

## Interpretação e limites

Um cabeçalho ausente é um indicador a analisar, não a confirmação de uma vulnerabilidade. Uma política presente pode estar mal configurada. SPF/DMARC podem não ser necessários num domínio que não envia correio; DMARC pode ser herdado. Nomes CT são históricos e podem já não estar ativos. A amostra do Internet Archive não é um inventário completo ou necessariamente recente. A localização IP é aproximada e não identifica uma pessoa ou morada.

Os registos RDAP podem ocultar campos; alguns serviços não têm registos próprios para subdomínios. Não se tenta adivinhar o domínio organizacional sem uma Public Suffix List. A consulta RDAP nesses casos pode devolver 404. Contactos pessoais não são extraídos dos vCards do RDAP.

Os fornecedores externos têm os seus próprios limites e termos. Antes de comercializar um serviço baseado nestas APIs, confirmar as respetivas condições e licenças. A aplicação mostra falhas por fonte em vez de apresentar dados inventados. Corpos HTTP são limitados a 512 KiB, documentos a excertos de 12 000 caracteres, respostas JSON a 2 MiB (CT: 4 MiB). JSON truncado é rejeitado para não ser apresentado como completo.

## Rede, privacidade e execução

Não há persistência de pesquisas no servidor, nem histórico em localStorage. Fornecedores recebem as consultas e o site recebe pedidos HTTP/TLS. Não são registados alvos nem relatórios nos logs da aplicação. Cookies devolvidos pelo site são excluídos do relatório. Exportações são ficheiros criados pelo utilizador.

São necessários:

- HTTPS para `dns.google`, `ipwho.is`, `data.iana.org`, `crt.sh`, `web.archive.org` e o serviço RDAP indicado pelo bootstrap IANA para o alvo.
- DNS e saída TCP direta 80/443 para os sites consultados. HTTP e TLS ligam a um IP público validado, preservando Host/SNI e a verificação do certificado.

Redes privadas, reservadas, URLs com credenciais e portas diferentes de 80/443 são rejeitadas. Todos os redirecionamentos HTTP são novamente validados; documentos não seguem redirecionamentos para outro site. A aplicação não faz exploração, port scanning nem consultas autenticadas.

O servidor destina-se a um ambiente de desenvolvimento de confiança. Para exposição pública são necessários autenticação, HTTPS e limites por utilizador num reverse proxy. Há um máximo de quatro pesquisas em simultâneo e oito workers de consulta; cada pedido de rede tem timeout, mas o DNS do sistema depende do resolver do sistema operativo. O tempo de uma pesquisa não é garantido.

### Estado de validação no ambiente cloud

A interface, a API e os parsers foram validados com testes e respostas controladas. Neste ambiente, os pedidos reais aos fornecedores devolvem bloqueio HTTP 403 do proxy e a resolução DNS pública pode falhar. Isto impede confirmar a integração externa completa aqui; as permissões têm de ser aplicadas nas definições do ambiente. Ter o servidor a responder não prova que as fontes externas estejam acessíveis. Num computador local é necessária internet e acesso aos destinos acima.

## Desenvolvimento e testes

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Os testes cobrem parsing de alvos, rejeição de redes privadas, API HTTP, falhas parciais, fontes aprofundadas, âmbito de nomes CT, descoberta limitada ao mesmo site, RDAP e análise de cabeçalhos. Não precisam de acesso externo. Não existe etapa de compilação.
