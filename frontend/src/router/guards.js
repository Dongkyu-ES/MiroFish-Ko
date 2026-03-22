/**
 * Thin navigation guards — 404 existence checks only.
 * Complex state-based routing stays in each view's onMounted.
 *
 * Error handling:
 *   - HTTP 404 → redirect to Home (entity not found)
 *   - All other errors (network, timeout, success:false) → fail-open (return true)
 */
import { getProject } from '../api/graph'
import { getSimulation } from '../api/simulation'
import { getReport } from '../api/report'

export async function guardProcess(to) {
  const projectId = to.params.projectId
  if (projectId === 'new') return true
  if (!projectId || projectId === 'undefined' || projectId === 'null') {
    console.warn(`[Guard] Invalid projectId: ${projectId}`)
    return { name: 'Home' }
  }
  try {
    await getProject(projectId)
    return true
  } catch (err) {
    if (err.response?.status === 404) {
      console.warn(`[Guard] Project not found: ${projectId}`)
      return { name: 'Home' }
    }
    return true // fail-open
  }
}

export async function guardSimulation(to) {
  const simulationId = to.params.simulationId
  if (!simulationId || simulationId === 'undefined' || simulationId === 'null') {
    console.warn(`[Guard] Invalid simulationId: ${simulationId}`)
    return { name: 'Home' }
  }
  try {
    await getSimulation(simulationId)
    return true
  } catch (err) {
    if (err.response?.status === 404) {
      console.warn(`[Guard] Simulation not found: ${simulationId}`)
      return { name: 'Home' }
    }
    return true
  }
}

export async function guardSimulationRun(to) {
  const simulationId = to.params.simulationId
  if (!simulationId || simulationId === 'undefined' || simulationId === 'null') {
    console.warn(`[Guard] Invalid simulationId: ${simulationId}`)
    return { name: 'Home' }
  }
  try {
    await getSimulation(simulationId)
    return true
  } catch (err) {
    if (err.response?.status === 404) {
      console.warn(`[Guard] Simulation not found: ${simulationId}`)
      return { name: 'Home' }
    }
    return true
  }
}

export async function guardReport(to) {
  const reportId = to.params.reportId
  if (!reportId || reportId === 'undefined' || reportId === 'null') {
    console.warn(`[Guard] Invalid reportId: ${reportId}`)
    return { name: 'Home' }
  }
  try {
    await getReport(reportId)
    return true
  } catch (err) {
    if (err.response?.status === 404) {
      console.warn(`[Guard] Report not found: ${reportId}`)
      return { name: 'Home' }
    }
    return true
  }
}

export async function guardInteraction(to) {
  const reportId = to.params.reportId
  if (!reportId || reportId === 'undefined' || reportId === 'null') {
    console.warn(`[Guard] Invalid reportId: ${reportId}`)
    return { name: 'Home' }
  }
  try {
    await getReport(reportId)
    return true
  } catch (err) {
    if (err.response?.status === 404) {
      console.warn(`[Guard] Report not found: ${reportId}`)
      return { name: 'Home' }
    }
    return true
  }
}
