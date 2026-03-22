import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Process from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import ReportView from '../views/ReportView.vue'
import InteractionView from '../views/InteractionView.vue'
import { guardProcess, guardSimulation, guardSimulationRun, guardReport, guardInteraction } from './guards'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true,
    meta: { guard: guardProcess }
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true,
    meta: { guard: guardSimulation }
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true,
    meta: { guard: guardSimulationRun }
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true,
    meta: { guard: guardReport }
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true,
    meta: { guard: guardInteraction }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 무한 리다이렉트 방지 — 모듈 레벨 카운터
let redirectCount = 0

router.beforeEach(async (to) => {
  if (redirectCount >= 3) {
    redirectCount = 0
    console.warn('[Guard] Redirect loop detected, bailing to Home')
    return { name: 'Home' }
  }

  const guard = to.meta?.guard
  if (!guard) {
    redirectCount = 0
    return true
  }

  const result = await guard(to)
  if (result === true) {
    redirectCount = 0
    return true
  }

  redirectCount++
  return result
})

export default router
