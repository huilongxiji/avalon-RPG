// 规则草稿的状态：生效版本、草稿、能不能修改；页面看草稿还是看生效版本；改动后通知页面重新读取
import { defineStore } from 'pinia'
import { fetchDraftState, type DraftState } from '@/api/edit'

export const useRulesStore = defineStore('rules', {
  state: () => ({
    state: null as DraftState | null,
    viewDraft: true, // 有草稿时默认看草稿
    revision: 0, // 每次修改后加 1，页面据此重新读取
    error: '',
  }),
  getters: {
    hasDraft: (s) => !!s.state?.draft,
    editable: (s) => !!s.state?.editable,
    publishable: (s) => !!s.state?.publishable,
    /** 页面读取数据时是否带 draft=true */
    useDraft(): boolean {
      return this.hasDraft && this.viewDraft
    },
    /** 现在能不能点编辑 */
    canEdit(): boolean {
      return this.editable && this.hasDraft && this.viewDraft
    },
    /** 不能编辑时的原因（按钮上的提示） */
    whyNot(): string {
      if (!this.editable) return '当前账号只有查看权限，需要编辑者或更高权限'
      if (!this.hasDraft) return '先点上方的「新建草稿」，改动都写在草稿里，激活后才生效'
      if (!this.viewDraft) return '现在看的是生效版本，切换到「草稿」才能修改'
      return ''
    },
  },
  actions: {
    async refresh() {
      try {
        this.state = await fetchDraftState()
        this.error = ''
      } catch (e) {
        this.error = (e as Error).message
      }
    },
    /** 改动保存之后调用 */
    async changed() {
      this.revision++
      await this.refresh()
    },
  },
})
