<template>
  <section class="path-locator" data-testid="path-locator" aria-label="路径定位与一致性复核发起区">
    <div class="locator-head">
      <div>
        <h3>路径定位与复核发起</h3>
        <p>先按父节点收窄候选，再用稳定节点 ID 定位实际地区；同名地区不会共用选择或说明。</p>
      </div>
      <div class="locator-head-actions">
        <span class="todo-pill" data-testid="review-todo-count">复核待办 {{ pendingReviewCount }}</span>
        <button class="btn ghost" type="button" data-testid="refresh-locator" @click="refreshAll">刷新定位</button>
      </div>
    </div>

    <div v-if="bannerMessage" class="locator-banner" :class="{ error: bannerError }" data-testid="locator-message">
      <span>{{ bannerMessage }}</span>
    </div>

    <div class="locator-grid">
      <div class="locator-card">
        <form class="locator-search" data-testid="locator-search" @submit.prevent="searchCandidates">
          <label class="locator-field">
            <span>父节点过滤</span>
            <select v-model="parentFilter" data-testid="parent-filter" @change="searchCandidates">
              <option value="">全部父节点</option>
              <option v-for="node in parentOptions" :key="node.id" :value="node.id">
                {{ node.path_text || node.name }}
              </option>
            </select>
          </label>
          <label class="locator-field grow">
            <span>地区名称检索</span>
            <input
              v-model="keyword"
              data-testid="region-search"
              type="search"
              placeholder="按地区名称检索，如：朝阳区"
              @input="scheduleCandidateSearch"
            />
          </label>
          <label class="check-field">
            <input v-model="gapOnly" type="checkbox" data-testid="gap-only" @change="searchCandidates" />
            <span>只看缺口地区</span>
          </label>
          <button class="btn primary" type="submit" data-testid="search-regions">检索候选</button>
          <button class="btn" type="button" data-testid="expand-all" @click="expandAll">全部展开</button>
        </form>

        <div class="candidate-panel" data-testid="candidate-panel">
          <div class="panel-title">
            <strong>候选地区</strong>
            <span data-testid="candidate-count">{{ candidates.length }} 条</span>
          </div>
          <div v-if="candidates.length" class="candidate-list" data-testid="candidate-list">
            <div
              v-for="candidate in candidates"
              :key="candidate.id"
              class="candidate-item"
              :class="{ active: candidate.id === selectedId }"
              :data-node-id="candidate.id"
              :data-parent-id="candidate.parent_id ?? ''"
              data-testid="candidate-item"
            >
              <button
                type="button"
                class="candidate-main"
                :data-testid="`candidate-${candidate.id}`"
                @click="locateCandidate(candidate)"
              >
                <span class="candidate-name">
                  {{ candidate.name }}
                  <em v-if="candidate.gap" class="gap-badge">缺口</em>
                </span>
                <small>{{ candidate.path_text }}</small>
              </button>
              <button
                class="btn small"
                type="button"
                :data-testid="`locate-${candidate.id}`"
                @click="locateCandidate(candidate)"
              >
                定位
              </button>
            </div>
          </div>
          <p v-else class="inline-empty" data-testid="candidate-empty">没有符合父节点和名称条件的候选地区。</p>
        </div>

        <div class="tree-panel" data-testid="hier-tree" role="tree" aria-label="地区层级树">
          <div
            v-for="item in visibleNodes"
            :key="item.node.id"
            class="tree-row"
            :class="{ selected: item.node.id === selectedId, located: item.node.id === flashId }"
            :data-node-id="item.node.id"
            :data-parent-id="item.node.parent_id ?? ''"
            :data-depth="item.depth"
            :data-testid="`tree-node-${item.node.id}`"
            :style="{ paddingLeft: `${8 + item.depth * 18}px` }"
            role="treeitem"
            :aria-selected="item.node.id === selectedId"
          >
            <button
              v-if="item.node.children?.length"
              type="button"
              class="tree-toggle"
              :aria-expanded="!!expanded[item.node.id]"
              :data-testid="`toggle-${item.node.id}`"
              @click="toggleNode(item.node.id)"
            >
              {{ expanded[item.node.id] ? '▾' : '▸' }}
            </button>
            <span v-else class="tree-toggle spacer" />
            <button
              type="button"
              class="tree-name"
              :data-testid="`select-node-${item.node.id}`"
              @click="chooseNode(item.node.id)"
            >
              {{ item.node.name }}
              <em v-if="item.node.gap" class="gap-dot" :title="String(item.node.gap_reason || '存在核对缺口')">!</em>
            </button>
            <span class="tree-code">{{ item.node.code }}</span>
            <button
              v-if="item.node.children?.length"
              type="button"
              class="link tiny"
              :data-testid="`expand-${item.node.id}`"
              @click="expandNode(item.node.id)"
            >
              展开
            </button>
            <button
              v-if="item.node.parent_id"
              type="button"
              class="link tiny danger"
              :data-testid="`move-${item.node.id}`"
              @click="quickMove(item.node.id)"
            >
              移走
            </button>
          </div>
        </div>
      </div>

      <aside class="locator-card detail-card">
        <template v-if="selectedNode">
          <div class="detail-title">
            <div>
              <h4 data-testid="selected-region-name">{{ selectedNode.name }}</h4>
              <p class="muted">稳定节点 ID：<code data-testid="selected-node-id">{{ selectedNode.id }}</code></p>
            </div>
            <span v-if="selectedNode.gap" class="gap-badge large">核对缺口地区</span>
          </div>

          <dl class="path-definition">
            <div>
              <dt>当前路径</dt>
              <dd data-testid="current-path" :data-path="currentPathText">{{ currentPathText }}</dd>
            </div>
            <div v-if="selectedNode.parent_id" class="parent-filter-action">
              <dt>当前父节点</dt>
              <dd>
                <button type="button" class="btn small" data-testid="filter-by-current-parent" @click="filterByCurrentParent">
                  按当前父节点过滤候选
                </button>
              </dd>
            </div>
            <div v-if="activeReview">
              <dt>提交时路径（那次提交）</dt>
              <dd data-testid="submitted-path" :data-path="activeReview.submitted_path_text">
                {{ activeReview.submitted_path_text }}
              </dd>
            </div>
            <div v-if="activeReview?.relinked_path_text">
              <dt>改挂办理路径</dt>
              <dd data-testid="relinked-path">{{ activeReview.relinked_path_text }}</dd>
            </div>
            <div v-if="selectedNode.gap_reason">
              <dt>缺口原因</dt>
              <dd>{{ selectedNode.gap_reason }}</dd>
            </div>
          </dl>

          <div class="move-box" data-testid="move-panel">
            <div class="move-actions">
              <button class="btn small" type="button" data-testid="move-parent" @click="moveSelectedParent">
                移走父节点
              </button>
              <button class="btn small" type="button" data-testid="move-node" @click="quickMove(selectedId)">
                移走此节点
              </button>
            </div>
            <label class="move-target">
              <span>改挂到指定父节点</span>
              <select v-model="moveTarget" data-testid="move-target">
                <option value="relocated-parent">迁移托管区</option>
                <option v-for="node in parentOptions" :key="`move-${node.id}`" :value="node.id">
                  {{ node.path_text || node.name }}
                </option>
              </select>
            </label>
            <button class="btn small ghost" type="button" data-testid="confirm-move" @click="moveSelectedToTarget">
              确认移动
            </button>
          </div>

          <div v-if="activeReview" class="review-status-card" :data-testid="`review-card-${activeReview.id}`">
            <div class="review-card-head">
              <strong data-testid="review-code">{{ activeReview.code }}</strong>
              <span class="status-pill" :data-status="activeReview.status" data-testid="review-status">
                {{ activeReview.status }}
              </span>
            </div>
            <p class="linked-todo" data-testid="linked-conform">
              待办已生成，并联动一致性核对工作台：{{ activeReview.conform_code }}
            </p>
            <p class="guidance" data-testid="scope-guidance">{{ activeReview.guidance }}</p>
            <div class="conflict-flags">
              <span v-if="activeReview.path_changed" class="flag warning" data-testid="path-changed-flag">路径已变更</span>
              <span v-if="activeReview.conflict" class="flag danger" data-testid="scope-conflict-flag">办理范围冲突</span>
              <span v-if="activeReview.can_complete_original" class="flag ok" data-testid="original-scope-allowed">
                可沿原范围办结
              </span>
              <span v-if="activeReview.must_relink" class="flag danger" data-testid="must-relink-flag">
                须改挂新路径后办结
              </span>
            </div>

            <label class="note-field">
              <span>复核说明（按申请 / 节点隔离保存）</span>
              <textarea
                v-model="note"
                rows="5"
                data-testid="review-note"
                placeholder="请输入复核说明或办结意见；可随时补填，内容按当前申请与节点隔离保存"
                @input="onNoteInput"
                @blur="() => void persistReviewDraft()"
              />
            </label>
            <p class="draft-hint" data-testid="draft-hint">{{ draftHint }}</p>

            <div class="review-actions">
              <RouterLink
                class="btn"
                :to="`/conform_check?review=${activeReview.id}`"
                data-testid="goto-conform"
              >
                前往一致性核对工作台
              </RouterLink>
              <button
                v-if="activeReview.status === '待签收'"
                class="btn primary"
                type="button"
                data-testid="claim-review"
                @click="claimCurrentReview"
              >
                签收
              </button>
              <button
                class="btn"
                type="button"
                data-testid="relink-review"
                :disabled="activeReview.status === '已办结'"
                @click="relinkCurrentReview"
              >
                改挂新路径
              </button>
              <button
                class="btn primary"
                type="button"
                data-testid="complete-original"
                :disabled="!activeReview.can_complete_original"
                :title="activeReview.can_complete_original ? '使用签收时锁定的原节点范围办结' : '当前不能沿原范围办结'"
                @click="completeCurrentReview('original')"
              >
                沿原范围办结
              </button>
              <button
                class="btn primary"
                type="button"
                data-testid="complete-relink"
                :disabled="activeReview.status === '已办结'"
                @click="completeCurrentReview('relink')"
              >
                改挂新路径并办结
              </button>
            </div>
          </div>

          <form v-else class="new-review-form" data-testid="new-review-form" @submit.prevent="submitReview">
            <label class="note-field">
              <span>复核说明</span>
              <textarea
                v-model="note"
                rows="5"
                required
                data-testid="review-note-input"
                placeholder="请输入复核说明：描述缺口地区、一致性口径和复核要求；离开或提交失败后会保留"
                @input="onNoteInput"
              />
            </label>
            <p class="draft-hint" data-testid="new-draft-hint">{{ draftHint }}</p>
            <div class="review-actions">
              <button class="btn primary" type="submit" data-testid="create-review" :disabled="submitting">
                {{ submitting ? '提交中…' : '发起复核' }}
              </button>
              <button class="btn primary" type="submit" data-testid="generate-todo" :disabled="submitting">
                {{ submitting ? '生成中…' : '生成待办' }}
              </button>
              <button
                v-if="errorMessage"
                class="btn primary"
                type="button"
                data-testid="retry-review"
                :disabled="submitting"
                @click="submitReview"
              >
                {{ submitting ? '重试中…' : '重试提交' }}
              </button>
            </div>
          </form>
        </template>

        <div v-else class="empty-detail" data-testid="locator-empty">
          <h4>请展开父节点并选择地区</h4>
          <p>可先在上方选择父节点并检索地区名称；候选中的完整路径会帮助区分同名地区。</p>
        </div>
      </aside>
    </div>

    <section class="review-list-card" data-testid="path-review-list">
      <div class="panel-title">
        <h4>路径复核申请</h4>
        <span>每条申请独立保存所选父节点、提交路径和说明草稿</span>
      </div>
      <div v-if="reviews.length" class="review-list">
        <article
          v-for="review in reviews"
          :key="review.id"
          class="review-list-item"
          :class="{ active: activeReview?.id === review.id }"
          :data-testid="`review-list-${review.id}`"
          :data-node-id="review.node_id"
        >
          <button type="button" class="review-open" :data-testid="`open-review-${review.id}`" @click="openReview(review.id)">
            <strong>{{ review.code }}</strong>
            <span>{{ review.node_name }}（{{ review.submitted_parent_name }}）</span>
            <small>提交：{{ review.submitted_path_text }}</small>
            <small>当前：{{ review.current_path_text }}</small>
          </button>
          <span class="status-pill" :data-status="review.status">{{ review.status }}</span>
          <RouterLink
            class="link"
            :to="`/conform_check?review=${review.id}`"
            :data-testid="`review-workbench-${review.id}`"
          >
            核对工作台
          </RouterLink>
        </article>
      </div>
      <p v-else class="inline-empty">暂无路径复核申请。</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  claimReview,
  completeReview,
  createReview,
  getCandidates,
  getReview,
  getTree,
  listReviews,
  moveNode,
  relinkReview,
  saveReviewDraft,
  type PathNode,
  type PathReview,
} from '@/api/pathReview'

const route = useRoute()
const router = useRouter()

const tree = ref<PathNode[]>([])
const flatNodes = ref<PathNode[]>([])
const candidates = ref<PathNode[]>([])
const reviews = ref<PathReview[]>([])
const activeReview = ref<PathReview | null>(null)

const expanded = ref<Record<string, boolean>>({})
const selectedId = ref('')
const flashId = ref('')
const keyword = ref('')
const parentFilter = ref('')
const gapOnly = ref(false)
const moveTarget = ref('relocated-parent')

const note = ref('')
const clientRef = ref('')
const submitting = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const draftHint = ref('说明会按申请和实际节点隔离保存')
const canRetry = ref(false)
const bannerMessage = computed(() => errorMessage.value || successMessage.value)
const bannerError = computed(() => !!errorMessage.value)

let searchTimer: ReturnType<typeof setTimeout> | undefined
let flashTimer: ReturnType<typeof setTimeout> | undefined
let draftPatchTimer: ReturnType<typeof setTimeout> | undefined

const DRAFT_STORAGE_PREFIX = 'hier-path:draft:v1:'

type LocalDraft = { note?: string; clientRef?: string; updatedAt?: string }

function storageKey(context: string): string {
  return `${DRAFT_STORAGE_PREFIX}${context}`
}

function readLocalDraft(context: string): LocalDraft {
  if (!context) return {}
  try {
    return JSON.parse(localStorage.getItem(storageKey(context)) || '{}') as LocalDraft
  } catch {
    return {}
  }
}

function writeLocalDraft(context: string, draft: LocalDraft): void {
  if (!context) return
  try {
    const previous = readLocalDraft(context)
    localStorage.setItem(storageKey(context), JSON.stringify({ ...previous, ...draft }))
  } catch {
    // localStorage 不可用时仍保留当前组件状态；刷新持久化是增强能力。
  }
}

function removeLocalDraft(context: string): void {
  try {
    localStorage.removeItem(storageKey(context))
  } catch {
    // ignore
  }
}

function newClientRef(nodeId: string): string {
  const random = Math.random().toString(36).slice(2, 10)
  return `browser-${nodeId}-${Date.now()}-${random}`
}

const selectedNode = computed<PathNode | undefined>(() =>
  flatNodes.value.find((node) => node.id === selectedId.value),
)

const currentPathText = computed(() => {
  if (!selectedNode.value) return ''
  const path: string[] = []
  let current: PathNode | undefined = selectedNode.value
  const guard = new Set<string>()
  while (current && !guard.has(current.id)) {
    guard.add(current.id)
    path.unshift(current.name)
    const parentId: string = current.parent_id ? String(current.parent_id) : ''
    current = parentId ? flatNodes.value.find((node) => node.id === parentId) : undefined
  }
  return path.join(' / ')
})

const parentOptions = computed(() =>
  flatNodes.value
    .filter((node) => {
      const hasChild = flatNodes.value.some((item) => item.parent_id === node.id)
      return Boolean(
        node.children?.length
        || hasChild
        || node.kind === 'parent'
        || node.kind === 'region-group',
      )
    })
    .map((node) => ({ ...node, path_text: nodePathText(node.id) })),
)

const visibleNodes = computed(() => {
  const result: { node: PathNode; depth: number }[] = []
  const walk = (nodes: PathNode[], depth: number) => {
    for (const node of nodes) {
      result.push({ node, depth })
      if (node.children?.length && expanded.value[node.id]) {
        walk(node.children, depth + 1)
      }
    }
  }
  walk(tree.value, 0)
  return result
})

const pendingReviewCount = computed(() =>
  reviews.value.filter((review) => review.status !== '已办结').length,
)

function nodePathText(nodeId: string): string {
  const names: string[] = []
  let current = flatNodes.value.find((node) => node.id === nodeId)
  const seen = new Set<string>()
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    names.unshift(current.name)
    const parentId: string = current.parent_id ? String(current.parent_id) : ''
    current = parentId ? flatNodes.value.find((node) => node.id === parentId) : undefined
  }
  return names.join(' / ')
}

async function loadTree(selectId?: string): Promise<void> {
  const payload = await getTree()
  tree.value = payload.items
  flatNodes.value = payload.nodes
  for (const node of payload.nodes) {
    if (node.children?.length) expanded.value[node.id] = true
  }
  if (selectId) {
    selectedId.value = selectId
    expandAncestors(selectId)
  }
}

async function searchCandidates(): Promise<void> {
  try {
    const payload = await getCandidates({
      name: keyword.value,
      parent_id: parentFilter.value,
      gap_only: gapOnly.value,
    })
    candidates.value = payload.items
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '候选地区读取失败'
  }
}

function scheduleCandidateSearch(): void {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void searchCandidates(), 180)
}

function expandAncestors(nodeId: string): void {
  let current = flatNodes.value.find((node) => node.id === nodeId)
  const seen = new Set<string>()
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    if (current.parent_id) expanded.value[String(current.parent_id)] = true
    current = current.parent_id
      ? flatNodes.value.find((node) => node.id === current?.parent_id)
      : undefined
  }
  expanded.value[nodeId] = true
}

function toggleNode(nodeId: string): void {
  expanded.value[nodeId] = !expanded.value[nodeId]
}

function expandNode(nodeId: string): void {
  // 幂等展开：自动化或用户点击“展开”时不会把已打开的树再收起。
  expanded.value[nodeId] = true
  expandAncestors(nodeId)
}

function expandAll(): void {
  for (const node of flatNodes.value) {
    if (node.children?.length) expanded.value[node.id] = true
  }
}

async function filterByCurrentParent(): Promise<void> {
  const parentId = selectedNode.value?.parent_id ? String(selectedNode.value.parent_id) : selectedId.value
  parentFilter.value = parentId
  keyword.value = selectedNode.value?.name ? String(selectedNode.value.name) : keyword.value
  await searchCandidates()
  successMessage.value = '已按当前父节点收窄候选，请从候选中选择实际地区'
}

function flashNode(nodeId: string): void {
  flashId.value = nodeId
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => { flashId.value = '' }, 1800)
  requestAnimationFrame(() => {
    document.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`)?.scrollIntoView({
      block: 'nearest',
      behavior: 'smooth',
    })
  })
}

async function chooseNode(nodeId: string): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''
  selectedId.value = nodeId
  expandAncestors(nodeId)
  const node = flatNodes.value.find((item) => item.id === nodeId)
  if (node?.children?.length) expanded.value[nodeId] = true
  flashNode(nodeId)
  activeReview.value = null
  await updateRouteQuery({ node: nodeId, review: undefined })
  loadNoteContext()
}

async function locateCandidate(candidate: PathNode): Promise<void> {
  // 候选已经携带唯一 ID 和路径；即使 name 相同，也不会误选另一个父节点下的地区。
  parentFilter.value = candidate.parent_id ? String(candidate.parent_id) : parentFilter.value
  selectedId.value = candidate.id
  expandAncestors(candidate.id)
  flashNode(candidate.id)
  activeReview.value = null
  await updateRouteQuery({ node: candidate.id, review: undefined })
  loadNoteContext()
  successMessage.value = `已定位到实际地区：${candidate.path_text}`
}

async function updateRouteQuery(changes: Record<string, string | undefined>): Promise<void> {
  const query = { ...route.query } as Record<string, string>
  for (const [key, value] of Object.entries(changes)) {
    if (value === undefined || value === '') delete query[key]
    else query[key] = value
  }
  await router.replace({ path: '/hier_path', query })
}

function contextKey(): string {
  if (activeReview.value) {
    // 同时绑定申请 ID 与实际节点 ID：即使内存后端重启后申请 ID 被复用，
    // 也不能把旧父节点下的说明恢复到另一个同名地区。
    return `review:${activeReview.value.id}:node:${activeReview.value.node_id}`
  }
  if (selectedId.value) return `node:${selectedId.value}`
  return ''
}

function loadNoteContext(): void {
  const key = contextKey()
  if (activeReview.value) {
    const local = readLocalDraft(key)
    note.value = local.note
      ?? String(activeReview.value.draft_note || activeReview.value.note || '')
    draftHint.value = local.note !== undefined
      ? '已从本机恢复该申请未提交的说明草稿'
      : '该申请的说明按申请 ID 隔离'
    return
  }

  if (selectedId.value) {
    const local = readLocalDraft(key)
    note.value = local.note ?? ''
    clientRef.value = local.clientRef || newClientRef(selectedId.value)
    writeLocalDraft(key, { clientRef: clientRef.value })
    draftHint.value = local.note
      ? '已恢复该地区上次填写但未提交的说明'
      : '新说明只属于当前选中的实际地区和父节点'
    return
  }

  note.value = ''
  clientRef.value = ''
  draftHint.value = '说明会按申请和实际节点隔离保存'
}

function onNoteInput(): void {
  const key = contextKey()
  if (!key) return
  if (activeReview.value) {
    writeLocalDraft(key, { note: note.value })
    draftHint.value = '草稿已保留在当前申请；失焦后同步到后端'
    if (draftPatchTimer) clearTimeout(draftPatchTimer)
    draftPatchTimer = setTimeout(() => void persistReviewDraft(true), 600)
  } else {
    writeLocalDraft(key, { note: note.value, clientRef: clientRef.value })
    draftHint.value = '已暂存到当前节点，切换、离开或请求失败都不会串到其他父节点'
  }
}

async function persistReviewDraft(silent = false): Promise<void> {
  if (!activeReview.value) return
  const key = contextKey()
  writeLocalDraft(key, { note: note.value })
  try {
    const result = await saveReviewDraft(activeReview.value.id, note.value)
    if (result.entry) activeReview.value = result.entry
  } catch (error) {
    if (!silent) {
      errorMessage.value = error instanceof Error ? error.message : '草稿同步失败，本机内容仍保留'
    }
  }
}

async function submitReview(): Promise<void> {
  if (!selectedId.value) {
    errorMessage.value = '请先展开父节点并选中一个实际地区'
    return
  }
  if (!note.value.trim()) {
    errorMessage.value = '请先填写一半或完整的复核说明，再生成待办'
    return
  }

  const nodeKey = `node:${selectedId.value}`
  const draft = readLocalDraft(nodeKey)
  if (!clientRef.value) clientRef.value = draft.clientRef || newClientRef(selectedId.value)
  writeLocalDraft(nodeKey, { note: note.value, clientRef: clientRef.value })

  submitting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  canRetry.value = true
  try {
    const result = await createReview({
      node_id: selectedId.value,
      note: note.value,
      client_ref: clientRef.value,
    })
    if (!result.ok || !result.entry) throw new Error(result.message || '复核待办生成失败')
    activeReview.value = result.entry
    writeLocalDraft(contextKey(), { note: note.value })
    removeLocalDraft(nodeKey)
    successMessage.value = result.message || '已生成待办并联动一致性核对工作台'
    await updateRouteQuery({ review: String(result.entry.id), node: result.entry.node_id })
    await loadReviews()
    draftHint.value = '申请已生成；说明绑定到该申请，而不是地区名称'
    canRetry.value = false
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求失败，已保留说明，可重试'
    draftHint.value = '提交失败：说明仍在当前申请中，可直接重试'
  } finally {
    submitting.value = false
  }
}

async function loadReviews(): Promise<void> {
  const payload = await listReviews()
  reviews.value = payload.items
}

async function openReview(reviewId: number | string): Promise<void> {
  errorMessage.value = ''
  const payload = await getReview(reviewId)
  if (!payload.entry) throw new Error('复核申请不存在')
  activeReview.value = payload.entry
  selectedId.value = payload.entry.node_id
  expandAncestors(selectedId.value)
  flashNode(selectedId.value)
  await updateRouteQuery({ review: String(reviewId), node: selectedId.value })
  loadNoteContext()
}

function queryValue(...keys: string[]): string {
  for (const key of keys) {
    const value = route.query[key]
    if (Array.isArray(value) && value[0]) return String(value[0])
    if (value) return String(value)
  }
  return ''
}

async function loadReviewFromRoute(): Promise<void> {
  const reviewId = queryValue('review', 'application', 'applicationId', 'request', 'requestId')
  if (reviewId) {
    try {
      const payload = await getReview(String(reviewId))
      if (payload.entry) {
        activeReview.value = payload.entry
        selectedId.value = payload.entry.node_id
        expandAncestors(selectedId.value)
        loadNoteContext()
        return
      }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '复核申请读取失败'
    }
  }
  activeReview.value = null
  const nodeId = queryValue('node', 'nodeId', 'region', 'regionId')
  if (nodeId && flatNodes.value.some((node) => node.id === nodeId)) {
    selectedId.value = nodeId
    expandAncestors(nodeId)
  }
  loadNoteContext()
}

async function refreshAll(): Promise<void> {
  loading.value = true
  try {
    await loadTree(selectedId.value || undefined)
    await Promise.all([searchCandidates(), loadReviews()])
    if (activeReview.value) {
      const payload = await getReview(activeReview.value.id)
      if (payload.entry) activeReview.value = payload.entry
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '定位数据刷新失败'
  } finally {
    loading.value = false
  }
}

async function quickMove(nodeId: string): Promise<void> {
  await performMove(nodeId, 'relocated-parent')
}

async function moveSelectedParent(): Promise<void> {
  const node = selectedNode.value
  if (!node?.parent_id) {
    errorMessage.value = '当前节点没有可移走的父节点'
    return
  }
  await performMove(String(node.parent_id), moveTarget.value || 'relocated-parent')
}

async function moveSelectedToTarget(): Promise<void> {
  if (!selectedId.value) return
  await performMove(selectedId.value, moveTarget.value)
}

async function performMove(nodeId: string, targetParentId: string): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const result = await moveNode(nodeId, targetParentId)
    successMessage.value = result.message || '节点已移动'
    await loadTree(selectedId.value)
    await loadReviews()
    if (activeReview.value) {
      const payload = await getReview(activeReview.value.id)
      if (payload.entry) activeReview.value = payload.entry
    }
    await searchCandidates()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '父节点移动失败'
  }
}

async function claimCurrentReview(): Promise<void> {
  if (!activeReview.value) return
  try {
    const result = await claimReview(activeReview.value.id)
    if (result.entry) activeReview.value = result.entry
    await loadReviews()
    successMessage.value = result.message || '已签收'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '签收失败'
  }
}

async function relinkCurrentReview(): Promise<void> {
  if (!activeReview.value) return
  try {
    await persistReviewDraft(true)
    const result = await relinkReview(activeReview.value.id)
    if (result.entry) activeReview.value = result.entry
    await loadReviews()
    successMessage.value = result.message || '已改挂到新路径'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '改挂失败'
  }
}

async function completeCurrentReview(mode: 'original' | 'relink'): Promise<void> {
  if (!activeReview.value) return
  try {
    await persistReviewDraft(true)
    const result = await completeReview(activeReview.value.id, {
      mode,
      completion_note: note.value,
      result: '确认一致',
    })
    if (result.entry) activeReview.value = result.entry
    await loadReviews()
    successMessage.value = result.message || '已办结，并已同步一致性核对工作台'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '办结失败'
  }
}

watch(
  () => [route.query.review, route.query.node],
  async ([reviewId, nodeId], oldValues) => {
    if (reviewId !== oldValues?.[0] && reviewId) {
      await loadReviewFromRoute()
      return
    }
    if (nodeId !== oldValues?.[1] && nodeId && !reviewId) {
      const id = String(nodeId)
      if (id !== selectedId.value) await chooseNode(id)
    }
  },
)

onMounted(async () => {
  try {
    await loadTree()
    await Promise.all([searchCandidates(), loadReviews()])
    await loadReviewFromRoute()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '路径定位初始化失败'
  }
})

defineExpose({ refreshAll })
</script>
