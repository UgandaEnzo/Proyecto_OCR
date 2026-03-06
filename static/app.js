// API key: can be provided via `window.__API_KEY__` or stored in localStorage under 'api_key'
// UI provides a button to set it; getHeaders() reads from localStorage at request time.

const { createApp } = Vue;

createApp({
  data() {
    return {
      pagos: [],
      q: '',
      page: 0,
      limit: 10,
      total: 0,
      editItem: null,
      editarModal: null,
      uploadModal: null
    }
  },
  computed: {
    totalPages() { return Math.max(1, Math.ceil(this.total / this.limit)) }
  },
  mounted() {
    this.editarModal = new bootstrap.Modal(document.getElementById('editarModal'))
    this.uploadModal = new bootstrap.Modal(document.getElementById('uploadModal'))
    this.bindUpload()
    this.cargar(0)
  },
  methods: {
    getHeaders() {
      const h = {}
      const key = window.__API_KEY__ || localStorage.getItem('api_key')
      if (key) h['x-api-key'] = key
      return h
    },

    promptApiKey() {
      try {
        const val = prompt('Introduce API Key (dejar vacío para desactivar)')
        if (val === null) return
        if (val === '') {
          localStorage.removeItem('api_key')
          delete window.__API_KEY__
          this.showToast('API key eliminada', 'info')
        } else {
          localStorage.setItem('api_key', val)
          window.__API_KEY__ = val
          this.showToast('API key guardada', 'success')
        }
      } catch (e) { console.error(e) }
    },
    showToast(message, type = 'info'){
      try{
        const container = document.getElementById('toastContainer')
        const toastEl = document.createElement('div')
        toastEl.className = `toast align-items-center text-bg-${type} border-0`
        toastEl.setAttribute('role','alert')
        toastEl.setAttribute('aria-live','assertive')
        toastEl.setAttribute('aria-atomic','true')
        toastEl.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`
        container.appendChild(toastEl)
        const toast = new bootstrap.Toast(toastEl, { delay: 4000 })
        toast.show()
        toastEl.addEventListener('hidden.bs.toast', ()=> toastEl.remove())
      }catch(e){ console.log('toast error', e) }
    },
    getUploadUrl(path) { return '/' + path.replace(/\\/g, '/') },
    async cargar(page) {
      this.page = Math.max(0, page)
      const offset = this.page * this.limit
      const base = this.q ? `/buscar-pagos/?q=${encodeURIComponent(this.q)}` : `/ver-pagos/`
      const sep = base.includes('?') ? '&' : '?'
      const url = `${base}${sep}limit=${this.limit}&offset=${offset}`
      try {
        const res = await fetch(url)
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        this.pagos = data.items || []
        this.total = data.total || this.pagos.length
      } catch (e) {
        console.error('Error cargar:', e)
        this.showToast('Error al cargar pagos', 'danger')
      }
    },
    async buscar() {
      this.page = 0
      await this.cargar(0)
    },
    formatMonto(m) {
      return new Intl.NumberFormat('es-VE', { style: 'currency', currency: 'VES' }).format(m)
    },
    openEditar(p) {
      this.editItem = Object.assign({}, p)
      this.editarModal.show()
    },
    async guardarEdicion() {
      if (!this.editItem) return
      const body = { referencia: this.editItem.referencia, banco_origen: this.editItem.banco_origen, monto: this.editItem.monto }
      const url = `/editar-pago-ref/${encodeURIComponent(this.editItem.referencia)}?confirm=true`
      try {
        const res = await fetch(url, { method: 'PUT', headers: Object.assign({'Content-Type':'application/json'}, this.getHeaders()), body: JSON.stringify(body) })
        const r = await res.json()
        this.showToast(r.mensaje || 'Editado', 'success')
        this.editarModal.hide()
        this.cargar(this.page)
      } catch (e) {
        console.error(e)
        this.showToast('Error al guardar', 'danger')
      }
    },
    async confirmEliminar(p) {
      if (!confirm('Eliminar pago id ' + p.id + ' ?')) return
      const url = `/eliminar-pago-ref/${encodeURIComponent(p.referencia)}?confirm=true`
      try {
        const res = await fetch(url, { method: 'DELETE', headers: this.getHeaders() })
        const r = await res.json()
        this.showToast(r.mensaje || 'Eliminado', 'success')
        this.cargar(this.page)
      } catch (e) {
        console.error(e)
        this.showToast('Error al eliminar', 'danger')
      }
    },
    bindUpload() {
      const btn = document.getElementById('uploadSubmit')
      const form = document.getElementById('uploadForm')
      btn.addEventListener('click', async () => {
        const input = form.querySelector('input[type=file]')
        if (!input.files.length) { this.showToast('Selecciona un archivo', 'warning'); return }
        const fd = new FormData(form)
        btn.disabled = true
        try {
          const res = await fetch('/subir-pago/', { method: 'POST', body: fd })
          let r
          try { r = await res.json() } catch(e){ r = { mensaje: await res.text() } }
          if (res.ok) {
            this.showToast(r.mensaje || 'Subido', 'success')
            this.uploadModal.hide()
            this.cargar(0)
          } else {
            this.showToast('Error al subir: ' + (r.mensaje || JSON.stringify(r)), 'danger')
          }
        } catch (e) {
          console.error(e)
          this.showToast('Error al subir: ' + (e.message || e), 'danger')
        } finally {
          btn.disabled = false
        }
      })
    }
  }
}).mount('#app')
