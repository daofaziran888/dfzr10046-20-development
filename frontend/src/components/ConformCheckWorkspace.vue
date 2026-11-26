<template>
  <section class="conform-panel" data-testid="conform-review-workbench" aria-label="路径复核联动工作台">
    <div class="locator-head">
      <div>
        <h3>一致性核对工作台 · 路径缺口复核待办</h3>
        <p>层级路径页发起的申请会在这里生成“待核对”条目；办结结果同步回一致性核对列表。</p>
      </div>
      <button class="btn" type="button" data-testid="refresh-conform-reviews" @click="load">刷新待办</button>
    </div>

    <p v-if="message" class="inline-message" :class="{ error: isError }" data-testid="conform-review-message">
      {{ message }}
    </p>

    <div v-if="highlightReview" class="highlight-review" :data-testid="`workbench-review-${highlightReview.id}`">
      <div class="review-card-head">
        <div>
          <strong data-testid="workbench-review-code">{{ highlightReview.code }}</strong>
          <span class="status-pill" :data-status="highlightReview.status">{{ highlightReview.status }}</span>
        </div>
        <RouterLink
          class="btn primary"
          :to="highlightReview.return_route || `/hier_path?review=${highlightReview.id}`"
          data-testid="back-to-source"
          aria-label="返回原位置"
        >
          返回原位置
        </RouterLink>
      </div>

      <div class="path-compare">
        <div>
          <span>地区</span>
          <strong :data-node-id="highlightReview.node_id" data-testid="workbench-node-name">
            {{ highlightReview.node_name }}
          </strong>
        </div>
        <div>
          <span>那次提交的路径</span>
          <p data-testid="workbench-submitted-path">{{ highlightReview.submitted_path_text }}</p>
        </div>
        <div>
          <span>当前路径</span>
          <p data-testid="workbench-current-path">{{ highlightReview.current_path_text }}</p>
        </div>
        <div v-if="highlightReview.relinked_path_text">
          <span>改挂办理路径</span>
          <p data-testid="workbench-relinked-path">{{ highlightReview.relinked_path_text }}</p>
        </div>
      </div>

      <p class="guidance" data-testid="workbench-guidance">{{ highlightReview.guidance }}</p>
      <div class="conflict-flags">
        <span v-if="highlightReview.path_changed" class="flag warning">路径已变更</span>
        <span v-if="highlightReview.conflict" class="flag danger" data-testid="workbench-scope-conflict">
          原办理范围冲突
        </span>
        <span v-if="highlightReview.can_complete_original" class="flag ok" data-testid="workbench-original-allowed">
          已签收，可沿原范围办结
        </span>
        <span v-if="highlightReview.must_relink" class="flag danger" data-testid="workbench-must-relink">
          须改挂新路径后才能办结
        </span>
      </div>

      <p v-if="highlightReview.note" class="review-note-readonly" data-testid="workbench-note">
        <span>复核说明：</span>{{ highlightReview.note }}
      </p>

      <div class="review-actions">
        <button
          v-if="highlightReview.status === '待签收'"
          class="btn primary"
          type="button"
          data-testid="workbench-claim"
          @click="claim(highlightReview.id)"
        >
          签收
        </button>
        <button
          class="btn"
          type="button"
          data-testid="workbench-relink"
          :disabled="highlightReview.status === '已办结'"
          @click="relink(highlightReview.id)"
        >
          改挂新路径
        </button>
        <button
          class="btn primary"
          type="button"
          data-testid="workbench-complete-original"
          :disabled="!highlightReview.can_complete_original"
          @click="complete(highlightReview.id, 'original')"
        >
          沿原范围办结
        </button>
        <button
          class="btn primary"
          type="button"
          data-testid="workbench-complete-relink"
          :disabled="highlightReview.status === '已办结'"
          @click="complete(highlightReview.id, 'relink')"
        >
          改挂新路径后办结
        </button>
      </div>
    </div>

    <div class="workbench-review-list" data-testid="conform-review-list">
      <article
        v-for="review in reviews"
        :key="review.id"
        class="workbench-review-item"
        :class="{ highlighted: String(review.id) === highlightId }"
        :data-testid="`conform-review-card-${review.id}`"
        :data-node-id="review.node_id"
      >
        <div class="review-summary">
          <strong>{{ review.code }} · {{ review.node_name }}</strong>
          <span class="status-pill" :data-status="review.status">{{ review.status }}</span>
          <small>提交路径：{{ review.submitted_path_text }}</small>
          <small>当前路径：{{ review.current_path_text }}</small>
          <small v-if="review.conform_code">联动核对单：{{ review.conform_code }}</small>
        </div>
        <div class="card-actions">
          <RouterLink
            class="link"
            :to="`/hier_path?review=${review.id}&node=${review.node_id}`"
            :data-testid="`card-back-to-source-${review.id}`"
          >
            返回原位置
          </RouterLink>
          <button class="link" type="button" :data-testid="`card-claim-${review.id}`" @click="claim(review.id)">
            签收
          </button>
          <button class="link" type="button" :data-testid="`card-complete-${review.id}`" @click="complete(review.id, review.must_relink ? 'relink' : 'original')">
            办结
          </button>
        </div>
      </article>
      <p v-if="!reviews.length" class="inline-empty">暂无路径复核待办，可从层级路径页定位缺口地区后发起复核。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  claimReview,
  completeReview,
  getReview,
  listReviews,
  relinkReview,
  type PathReview,
} from '@/api/pathReview'

const route = useRoute()
const reviews = ref<PathReview[]>([])
const highlightReview = ref<PathReview | null>(null)
const message = ref('')
const isError = ref(false)

const highlightId = computed(() => {
  for (const key of ['review', 'application', 'applicationId', 'request', 'requestId']) {
    const value = route.query[key]
    if (Array.isArray(value) && value[0]) return String(value[0])
    if (value) return String(value)
  }
  return ''
})

async function loadHighlight(): Promise<void> {
  if (!highlightId.value) {
    highlightReview.value = null
    return
  }
  try {
    const payload = await getReview(highlightId.value)
    highlightReview.value = payload.entry ?? null
  } catch (error) {
    message.value = error instanceof Error ? error.message : '复核申请读取失败'
    isError.value = true
  }
}

async function load(): Promise<void> {
  try {
    const payload = await listReviews()
    reviews.value = payload.items
    await loadHighlight()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '复核待办读取失败'
    isError.value = true
  }
}

async function claim(id: number): Promise<void> {
  try {
    const result = await claimReview(id)
    message.value = result.message || '已签收'
    isError.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '签收失败'
    isError.value = true
  }
}

async function relink(id: number): Promise<void> {
  try {
    const result = await relinkReview(id)
    message.value = result.message || '已改挂'
    isError.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '改挂失败'
    isError.value = true
  }
}

async function complete(id: number, mode: 'original' | 'relink'): Promise<void> {
  try {
    const result = await completeReview(id, { mode, result: '确认一致' })
    message.value = result.message || '已办结'
    isError.value = false
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '办结失败；若提示须改挂，请先改挂新路径'
    isError.value = true
  }
}

watch(highlightId, () => void loadHighlight())
onMounted(load)

defineExpose({ load })
</script>
