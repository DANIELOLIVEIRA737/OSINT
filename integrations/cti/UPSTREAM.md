# Integração CTI

Origem: https://github.com/DANIELOLIVEIRA737/cti
Commit integrado: ece2a175d6e837a9473031173cc2f4ccada06ced

A interface em static/cti mantém o mapa, camadas, paginação, filtros, exportação CSV e definições do projeto CTI. O adaptador cti.py implementa os feeds no servidor Python para manter um único processo e o arranque Windows sem exigir Node. Os parsers JavaScript originais e fixtures ficam aqui como referência e são usados nos testes de compatibilidade. O ranges.bin e centroids.json são os dados RIR do commit indicado; não são geolocalização em tempo real e não são atualizados automaticamente.

O projeto publicado em Cloudflare continua independente desta distribuição local. Não se fez deploy nem se alterou o repositório CTI original.

DShield/SANS: respeitar atribuição e termos CC BY-NC-SA (não comercial). URLhaus e Feodo: termos abuse.ch. OSM: atribuição OpenStreetMap contributors. Leaflet 1.9.4: BSD-2-Clause, licença em LEAFLET-LICENSE.txt. O world.geojson é o asset do projeto original, mantido com a proveniência acima.
