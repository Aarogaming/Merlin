/*
 * AUTO-GENERATED FILE - DO NOT EDIT.
 * Source: tests/fixtures/contracts/*.request.json + *.expected_response.json
 * Generator: scripts/generate_frontend_operation_contracts.py
 */

export const OPERATION_NAMES = [
  'assistant.chat.request',
  'assistant.chat.request.with_metadata',
  'assistant.tools.execute',
  'merlin.aas.create_task',
  'merlin.alerts.list',
  'merlin.command.execute',
  'merlin.context.get',
  'merlin.context.update',
  'merlin.dynamic_components.list',
  'merlin.genesis.logs',
  'merlin.genesis.manifest',
  'merlin.history.get',
  'merlin.llm.ab.complete',
  'merlin.llm.ab.create',
  'merlin.llm.ab.get',
  'merlin.llm.ab.list',
  'merlin.llm.ab.result',
  'merlin.llm.adaptive.feedback',
  'merlin.llm.adaptive.metrics',
  'merlin.llm.adaptive.reset',
  'merlin.llm.adaptive.status',
  'merlin.llm.cost.budget.get',
  'merlin.llm.cost.budget.set',
  'merlin.llm.cost.optimization.get',
  'merlin.llm.cost.pricing.set',
  'merlin.llm.cost.report',
  'merlin.llm.cost.thresholds.get',
  'merlin.llm.cost.thresholds.set',
  'merlin.llm.parallel.status',
  'merlin.llm.parallel.strategy',
  'merlin.llm.predictive.export',
  'merlin.llm.predictive.feedback',
  'merlin.llm.predictive.models',
  'merlin.llm.predictive.select',
  'merlin.llm.predictive.status',
  'merlin.plugins.execute',
  'merlin.plugins.list',
  'merlin.rag.query',
  'merlin.research.manager.brief.get',
  'merlin.research.manager.session.create',
  'merlin.research.manager.session.get',
  'merlin.research.manager.session.signal.add',
  'merlin.research.manager.sessions.list',
  'merlin.search.query',
  'merlin.system_info.get',
  'merlin.tasks.create',
  'merlin.tasks.list',
  'merlin.user_manager.authenticate',
  'merlin.user_manager.create',
  'merlin.voice.listen',
  'merlin.voice.status',
  'merlin.voice.synthesize',
  'merlin.voice.transcribe',
] as const;

export type OperationName = (typeof OPERATION_NAMES)[number];

export interface OperationContractFixture {
  requestFixture?: string;
  responseFixture?: string;
}

export const OPERATION_CONTRACT_FIXTURES: Record<OperationName, OperationContractFixture> = {
  'assistant.chat.request': {
    requestFixture: 'tests/fixtures/contracts/assistant.chat.request.json',
    responseFixture: 'tests/fixtures/contracts/assistant.chat.request.expected_response.json',
  },
  'assistant.chat.request.with_metadata': {
    requestFixture: undefined,
    responseFixture: 'tests/fixtures/contracts/assistant.chat.request.with_metadata.expected_response.json',
  },
  'assistant.tools.execute': {
    requestFixture: 'tests/fixtures/contracts/assistant.tools.execute.request.json',
    responseFixture: 'tests/fixtures/contracts/assistant.tools.execute.expected_response.json',
  },
  'merlin.aas.create_task': {
    requestFixture: 'tests/fixtures/contracts/merlin.aas.create_task.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.aas.create_task.expected_response.json',
  },
  'merlin.alerts.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.alerts.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.alerts.list.expected_response.json',
  },
  'merlin.command.execute': {
    requestFixture: 'tests/fixtures/contracts/merlin.command.execute.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.command.execute.expected_response.json',
  },
  'merlin.context.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.context.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.context.get.expected_response.json',
  },
  'merlin.context.update': {
    requestFixture: 'tests/fixtures/contracts/merlin.context.update.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.context.update.expected_response.json',
  },
  'merlin.dynamic_components.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.dynamic_components.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.dynamic_components.list.expected_response.json',
  },
  'merlin.genesis.logs': {
    requestFixture: 'tests/fixtures/contracts/merlin.genesis.logs.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.genesis.logs.expected_response.json',
  },
  'merlin.genesis.manifest': {
    requestFixture: 'tests/fixtures/contracts/merlin.genesis.manifest.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.genesis.manifest.expected_response.json',
  },
  'merlin.history.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.history.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.history.get.expected_response.json',
  },
  'merlin.llm.ab.complete': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.ab.complete.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.ab.complete.expected_response.json',
  },
  'merlin.llm.ab.create': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.ab.create.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.ab.create.expected_response.json',
  },
  'merlin.llm.ab.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.ab.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.ab.get.expected_response.json',
  },
  'merlin.llm.ab.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.ab.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.ab.list.expected_response.json',
  },
  'merlin.llm.ab.result': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.ab.result.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.ab.result.expected_response.json',
  },
  'merlin.llm.adaptive.feedback': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.feedback.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.feedback.expected_response.json',
  },
  'merlin.llm.adaptive.metrics': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.metrics.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.metrics.expected_response.json',
  },
  'merlin.llm.adaptive.reset': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.reset.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.reset.expected_response.json',
  },
  'merlin.llm.adaptive.status': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.status.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.adaptive.status.expected_response.json',
  },
  'merlin.llm.cost.budget.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.budget.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.budget.get.expected_response.json',
  },
  'merlin.llm.cost.budget.set': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.budget.set.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.budget.set.expected_response.json',
  },
  'merlin.llm.cost.optimization.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.optimization.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.optimization.get.expected_response.json',
  },
  'merlin.llm.cost.pricing.set': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.pricing.set.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.pricing.set.expected_response.json',
  },
  'merlin.llm.cost.report': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.report.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.report.expected_response.json',
  },
  'merlin.llm.cost.thresholds.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.thresholds.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.thresholds.get.expected_response.json',
  },
  'merlin.llm.cost.thresholds.set': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.cost.thresholds.set.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.cost.thresholds.set.expected_response.json',
  },
  'merlin.llm.parallel.status': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.parallel.status.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.parallel.status.expected_response.json',
  },
  'merlin.llm.parallel.strategy': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.parallel.strategy.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.parallel.strategy.expected_response.json',
  },
  'merlin.llm.predictive.export': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.predictive.export.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.predictive.export.expected_response.json',
  },
  'merlin.llm.predictive.feedback': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.predictive.feedback.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.predictive.feedback.expected_response.json',
  },
  'merlin.llm.predictive.models': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.predictive.models.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.predictive.models.expected_response.json',
  },
  'merlin.llm.predictive.select': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.predictive.select.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.predictive.select.expected_response.json',
  },
  'merlin.llm.predictive.status': {
    requestFixture: 'tests/fixtures/contracts/merlin.llm.predictive.status.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.llm.predictive.status.expected_response.json',
  },
  'merlin.plugins.execute': {
    requestFixture: 'tests/fixtures/contracts/merlin.plugins.execute.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.plugins.execute.expected_response.json',
  },
  'merlin.plugins.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.plugins.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.plugins.list.expected_response.json',
  },
  'merlin.rag.query': {
    requestFixture: 'tests/fixtures/contracts/merlin.rag.query.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.rag.query.expected_response.json',
  },
  'merlin.research.manager.brief.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.research.manager.brief.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.research.manager.brief.get.expected_response.json',
  },
  'merlin.research.manager.session.create': {
    requestFixture: 'tests/fixtures/contracts/merlin.research.manager.session.create.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.research.manager.session.create.expected_response.json',
  },
  'merlin.research.manager.session.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.research.manager.session.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.research.manager.session.get.expected_response.json',
  },
  'merlin.research.manager.session.signal.add': {
    requestFixture: 'tests/fixtures/contracts/merlin.research.manager.session.signal.add.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.research.manager.session.signal.add.expected_response.json',
  },
  'merlin.research.manager.sessions.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.research.manager.sessions.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.research.manager.sessions.list.expected_response.json',
  },
  'merlin.search.query': {
    requestFixture: 'tests/fixtures/contracts/merlin.search.query.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.search.query.expected_response.json',
  },
  'merlin.system_info.get': {
    requestFixture: 'tests/fixtures/contracts/merlin.system_info.get.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.system_info.get.expected_response.json',
  },
  'merlin.tasks.create': {
    requestFixture: 'tests/fixtures/contracts/merlin.tasks.create.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.tasks.create.expected_response.json',
  },
  'merlin.tasks.list': {
    requestFixture: 'tests/fixtures/contracts/merlin.tasks.list.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.tasks.list.expected_response.json',
  },
  'merlin.user_manager.authenticate': {
    requestFixture: 'tests/fixtures/contracts/merlin.user_manager.authenticate.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.user_manager.authenticate.expected_response.json',
  },
  'merlin.user_manager.create': {
    requestFixture: 'tests/fixtures/contracts/merlin.user_manager.create.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.user_manager.create.expected_response.json',
  },
  'merlin.voice.listen': {
    requestFixture: 'tests/fixtures/contracts/merlin.voice.listen.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.voice.listen.expected_response.json',
  },
  'merlin.voice.status': {
    requestFixture: 'tests/fixtures/contracts/merlin.voice.status.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.voice.status.expected_response.json',
  },
  'merlin.voice.synthesize': {
    requestFixture: 'tests/fixtures/contracts/merlin.voice.synthesize.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.voice.synthesize.expected_response.json',
  },
  'merlin.voice.transcribe': {
    requestFixture: 'tests/fixtures/contracts/merlin.voice.transcribe.request.json',
    responseFixture: 'tests/fixtures/contracts/merlin.voice.transcribe.expected_response.json',
  },
};

export function isKnownOperationName(name: string): name is OperationName {
  return (OPERATION_NAMES as readonly string[]).includes(name);
}
