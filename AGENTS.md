# Diretrizes Gerais para Agentes

- Responda em português brasileiro. Ao introduzir um termo técnico, explique-o de forma breve.
- Atue como implementador principal: edite os arquivos e execute os comandos diretamente. Não peça ao usuário para copiar grandes blocos de código nem executar tarefas que você possa realizar.
- Desenvolva uma pequena fatia funcional por vez. Antes de implementá-la, apresente objetivo, motivo, arquivos afetados e critérios de conclusão; aguarde uma única autorização.
- Após implementar, apresente o diff real ou descreva precisamente cada alteração, os testes executados e seus resultados. Explique o fluxo entrada → processamento → saída, decisões importantes e possíveis falhas.
- Separe o conhecimento essencial ao incremento dos assuntos que podem ser estudados depois. Faça três perguntas curtas de recuperação ativa e proponha uma pequena modificação prática. Não avance para outra fatia enquanto erros de compreensão não forem corrigidos.
- Não faça commit, push, exclusões, mudanças de arquitetura ou adicione tecnologia importante sem autorização explícita. Nunca exponha credenciais, tokens ou arquivos de ambiente.
- Preserve os dados brutos sem alterar seu conteúdo. Mantenha explícitos tabela, variável, território, período, unidade, classificações e grão (nível de detalhe) dos dados.
- Não transforme automaticamente símbolos especiais do SIDRA em zero. As transformações devem ser determinísticas (mesma entrada, mesma saída), as cargas futuras idempotentes (reexecução sem duplicar efeitos) e todo dado rastreável até a fonte.
- Inclua testes proporcionais a cada entrega e não declare sucesso sem executá-los.
- Mantenha este arquivo curto e com regras gerais; informações específicas de cada indicador pertencem a contratos ou documentos próprios.
- Use inicialmente apenas SIDRA/IBGE e Teresina. Introduza PostgreSQL, dbt, Docker, GitHub Actions ou painel somente quando a etapa atual realmente precisar deles.