import service, { requestWithRetry } from './index'

/**
 * 보고서 생성 시작
 * @param {Object} data - { simulation_id, force_regenerate? }
 */
export const generateReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/generate', data), 3, 1000)
}

/**
 * 보고서 생성 상태 조회
 * @param {string} reportId
 */
export const getReportStatus = (reportId) => {
  return service.get(`/api/report/generate/status`, { params: { report_id: reportId } })
}

/**
 * Agent 로그 조회(증분)
 * @param {string} reportId
 * @param {number} fromLine - 조회 시작 라인
 */
export const getAgentLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * 콘솔 로그 조회(증분)
 * @param {string} reportId
 * @param {number} fromLine - 조회 시작 라인
 */
export const getConsoleLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/**
 * 보고서 상세 조회
 * @param {string} reportId
 */
export const getReport = (reportId) => {
  return service.get(`/api/report/${reportId}`)
}

/**
 * 시뮬레이션 ID로 보고서 조회
 * @param {string} simulationId
 */
export const getReportBySimulation = (simulationId) => {
  return service.get(`/api/report/by-simulation/${simulationId}`)
}

/**
 * Report Agent와 대화
 * @param {Object} data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/chat', data), 3, 1000)
}
