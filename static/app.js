// API key: can be provided via `window.__API_KEY__` or stored in localStorage under 'api_key'
// UI provides a button to set it; getHeaders() reads from localStorage at request time.

const { createApp, ref, reactive, computed, onMounted } = Vue;

createApp({
  setup() {
    // --- Estado Reactivo ---
    const pagos = ref([]);
    const q = ref('');
    const page = ref(0);
    const limit = ref(10);
    const total = ref(0);

    const vistaActual = ref('pagos'); // 'pagos' o 'clientes'

    const procesandoSubida = ref(false);
    const uploadBank = ref('');
    const manualItem = reactive({ banco: '', referencia: '', monto: 0, cliente_id: null });    
    const nuevoCliente = reactive({ nombre: '', cedula: '', telefono: '' });
    const editandoCliente = ref(null);
    const qClientes = ref('');
    const clientes = ref([]);
    const clienteSeleccionado = ref(null);
    const pagosCliente = ref([]);
    const cargandoHistorialCliente = ref(false);
    const clienteTotales = reactive({ total_bs: 0, total_usd: 0, total_pagos: 0 });

    // --- Calculadora Bi-direccional ---
    const calcBs = ref(0);
    const calcUsd = ref(0);
    const tasaActualCalc = ref(1.0);
    const conversionResult = ref(null);

    const bancoFiltro = ref('');
    const reportPeriod = ref('mensual');
    const fechaInicio = ref('');
    const fechaFin = ref('');
    const reportes = ref([]);

    // --- Estados para el Chat IA ---
    const chatInput = ref('');
    const chatHistory = ref([]);
    const cargandoChat = ref(false);

    const historial = ref([]);
    const cargandoHistorial = ref(false);

    const imagenSeleccionada = ref('');
    const pagoSeleccionado = ref(null);

    // Referencias a Modales Bootstrap
    let uploadModal = null;
    let manualModal = null;
    let historialModal = null;
    let imagenModal = null;
    let clientesModal = null;
    let editarClienteModal = null;
    let historialClienteModal = null;

    // --- Computed ---
    const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)));
    const bancosDisponibles = ref([]);

    // --- Métodos Auxiliares ---
    const getHeaders = () => {
      const h = {};
      const key = window.__API_KEY__ || localStorage.getItem('api_key');
      if (key) h['x-api-key'] = key;
      return h;
    };

    const showToast = (message, type = 'info') => {
      try {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-bg-${type} border-0`;
        toastEl.setAttribute('role', 'alert');
        toastEl.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
        container.appendChild(toastEl);
        const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
      } catch (e) { console.log('toast error', e); }
    };

    const getUploadUrl = (path) => {
        if (!path) return '';
        return '/' + path.replace(/\\/g, '/');
    };

    const cargarBancos = async () => {
      try {
        const res = await fetch('/bancos/', { headers: getHeaders() });
        if (res.ok) {
          const data = await res.json();
          bancosDisponibles.value = data.bancos || [];
        }
      } catch (e) {
        console.error('Error cargando bancos:', e);
      }
    };

    const formatMonto = (m) => {
      const val = parseFloat(m) || 0;
      return new Intl.NumberFormat('es-VE', { style: 'currency', currency: 'VES' }).format(val);
    };

    const formatNumero = (value) => {
      const val = parseFloat(value) || 0;
      return new Intl.NumberFormat('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);
    };

    const formatDate = (value) => {
      if (!value) return 'N/A';
      return new Date(value).toLocaleDateString('es-VE');
    };

    const formatAccion = (a) => {
      const map = {
        'create_ia': '✨ Creación por IA',
        'create_manual': '👤 Registro Manual',
        'reprocess': '🔄 Re-procesado (OCR)',
        'delete': '🗑️ Eliminado',
        'update_status': '✍️ Cambio de Estado'
      };
      return map[a] || a;
    };

    const promptApiKey = () => {
        const val = prompt('Introduce API Key (dejar vacío para desactivar)');
        if (val === null) return;
        if (val === '') {
          localStorage.removeItem('api_key');
          delete window.__API_KEY__;
          showToast('API key eliminada', 'info');
        } else {
          localStorage.setItem('api_key', val);
          window.__API_KEY__ = val;
          showToast('API key guardada', 'success');
        }
    };

    // --- Lógica de Negocio ---

    const enviarConsultaIA = async () => {
        if (!chatInput.value.trim()) return;
        
        const pregunta = chatInput.value;
        chatHistory.value.push({ role: 'user', content: pregunta });
        chatInput.value = '';
        cargandoChat.value = true;

        try {
            const res = await fetch('/IA/consultar/', {
                method: 'POST',
                headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ pregunta: pregunta })
            });
            
            if (res.ok) {
                const data = await res.json();
                chatHistory.value.push({ role: 'assistant', content: data.respuesta });
            } else {
                showToast('La IA no pudo responder en este momento', 'danger');
            }
        } catch (e) {
            console.error(e);
            showToast('Error de conexión con el servicio de IA', 'danger');
        } finally {
            cargandoChat.value = false;
        }
    };

    const syncCalculadora = (origen) => {
        if (origen === 'bs') {
            calcUsd.value = calcBs.value > 0 ? (calcBs.value / tasaActualCalc.value).toFixed(2) : 0;
        } else {
            calcBs.value = calcUsd.value > 0 ? (calcUsd.value * tasaActualCalc.value).toFixed(2) : 0;
        }
    };

    const refrescarTasaCalculadora = async () => {
        const res = await fetch('/tasa-bcv/', { headers: getHeaders() });
        if (res.ok) {
            const data = await res.json();
            tasaActualCalc.value = data.tasa_bcv;
            syncCalculadora('bs');
        }
    };

    const cargarClientes = async () => {
        try {
            const url = qClientes.value ? `/clientes/?q=${encodeURIComponent(qClientes.value)}` : '/clientes/';
            const res = await fetch(url, { headers: getHeaders() });
            if (res.ok) {
                clientes.value = await res.json();
            }
        } catch (e) { console.error('Error cargando clientes:', e); }
    };

    const prepararEdicion = (cliente) => {
        editandoCliente.value = { ...cliente };
        if (editarClienteModal) editarClienteModal.show();
    };

    const guardarEdicion = async () => {
        if (!editandoCliente.value.nombre || !editandoCliente.value.cedula) {
            showToast('El nombre y la cédula son obligatorios.', 'warning');
            return;
        }
        const isNumeric = (val) => /^\d+$/.test(val);
        if (!isNumeric(editandoCliente.value.cedula) || (editandoCliente.value.telefono && !isNumeric(editandoCliente.value.telefono))) {
            showToast('La cédula y el teléfono deben ser estrictamente numéricos.', 'warning');
            return;
        }
        try {
            const res = await fetch(`/clientes/${editandoCliente.value.id}`, {
                method: 'PUT',
                headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(editandoCliente.value)
            });
            if (res.ok) {
                showToast('Cliente actualizado', 'success');
                if (editarClienteModal) editarClienteModal.hide();
                await cargarClientes();
            } else {
                const err = await res.json();
                showToast(`Error: ${err.detail}`, 'danger');
            }
        } catch (e) { showToast('Error de conexión', 'danger'); }
    };

    const eliminarCliente = async (id) => {
        if (!confirm('¿Seguro que deseas eliminar este cliente?')) return;
        try {
            const res = await fetch(`/clientes/${id}`, { method: 'DELETE', headers: getHeaders() });
            if (res.ok) {
                showToast('Cliente eliminado', 'info');
                await cargarClientes();
            }
        } catch (e) { showToast('Error al eliminar', 'danger'); }
    };

    const cargar = async (p) => {
      page.value = Math.max(0, p);
      const base = `/ver-pagos/`;
      const params = new URLSearchParams();
      params.set('page', page.value + 1);
      params.set('size', limit.value);
      if (q.value) params.set('q', q.value);
      if (bancoFiltro.value) params.set('banco', bancoFiltro.value);
      const url = `${base}?${params.toString()}`;
      try {
        const res = await fetch(url, { headers: getHeaders() });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        pagos.value = data.items || [];
        total.value = data.total || pagos.value.length;
      } catch (e) { console.error('Error cargar:', e); }
    };

    const buscar = async () => {
      page.value = 0;
      await cargar(0);
    };

    const cargarReportes = async () => {
      let url = `/reportes/?tipo_reporte=${encodeURIComponent(reportPeriod.value)}`;
      if (fechaInicio.value) {
          url += `&start_date=${encodeURIComponent(fechaInicio.value)}`;
      }
      if (fechaFin.value) {
          url += `&end_date=${encodeURIComponent(fechaFin.value)}`;
      }

      try {
          const res = await fetch(url, { headers: getHeaders() });
          if (!res.ok) throw new Error(await res.text());
          const data = await res.json();
          reportes.value = data.resultados || [];
      } catch (e) {
          console.error('Error cargar reportes:', e);
          reportes.value = [];
      }
    };

    const exportarReporte = async (formato) => {
        let url = `/reportes/export/?tipo_reporte=${encodeURIComponent(reportPeriod.value)}&format=${encodeURIComponent(formato)}`;
        if (fechaInicio.value) url += `&start_date=${encodeURIComponent(fechaInicio.value)}`;
        if (fechaFin.value) url += `&end_date=${encodeURIComponent(fechaFin.value)}`;

        try {
            const res = await fetch(url, { headers: getHeaders() });
            if (!res.ok) throw new Error(await res.text());

            const blob = await res.blob();
            const a = document.createElement('a');
            const extension = formato === 'pdf' ? 'pdf' : 'xlsx';
            a.href = URL.createObjectURL(blob);
            a.download = `reportes-${reportPeriod.value}.${extension}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(a.href);
            showToast(`Reporte exportado como ${extension.toUpperCase()}`, 'success');
        } catch (e) {
            console.error('Error exportar reporte:', e);
            showToast('No se pudo exportar el reporte', 'danger');
        }
    };

    const cambiarEstado = async (pagoId, nuevoEstado) => {
        try {
            const res = await fetch(`/pago/${pagoId}/estado`, {
                method: 'PATCH',
                headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ estado: nuevoEstado })
            });
            if (res.ok) {
                // Actualización optimista en la tabla
                const p = pagos.value.find(x => x.id === pagoId);
                if (p) p.estado = nuevoEstado;
                showToast(`Estado actualizado a ${nuevoEstado}`, 'success');
            } else {
                showToast('No se pudo actualizar el estado', 'danger');
            }
        } catch (e) {
            console.error(e);
            showToast('Error de conexión', 'danger');
        }
    };

    const guardarManual = async () => {
        if (!manualItem.banco || !manualItem.referencia) {
            showToast("Por favor llena los campos obligatorios", "warning");
            return;
        }
        try {
            const res = await fetch('/pago-manual/', {
                method: 'POST',
                headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(manualItem)
            });

            if (res.ok) {
                manualModal.hide();
                Object.assign(manualItem, { banco: '', referencia: '', monto: 0, cliente_id: null });
                cargar(0);
                showToast("¡Registro manual guardado!", 'success');
            } else {
                const errorData = await res.json();
                showToast("Error: " + (errorData.detail || errorData.mensaje || "No se pudo guardar"), "danger");
            }
        } catch (e) { console.error(e); }
    };

    const agregarCliente = async () => {
        if (!nuevoCliente.nombre || !nuevoCliente.cedula) {
            showToast('El nombre y la cédula son obligatorios.', 'warning');
            return;
        }
        const isNumeric = (val) => /^\d+$/.test(val);
        if (!isNumeric(nuevoCliente.cedula) || (nuevoCliente.telefono && !isNumeric(nuevoCliente.telefono))) {
            showToast('La cédula y el teléfono deben contener solo números.', 'warning');
            return;
        }
        try {
            const res = await fetch('/clientes/', {
                method: 'POST',
                headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(nuevoCliente)
            });
            if (res.ok) {
                showToast('Cliente agregado', 'success');
                Object.assign(nuevoCliente, { nombre: '', cedula: '', telefono: '' });
                await cargarClientes();
            } else {
                const err = await res.json();
                showToast(`Error: ${err.detail}`, 'danger');
            }
        } catch (e) { showToast('Error de conexión', 'danger'); }
    };

    // --- Modales y UI ---
    const abrirModalSubida = async () => {
        await cargarClientes();
        uploadModal.show();
    };

    const abrirModalManual = async () => {
        await cargarClientes();
        manualModal.show();
    };

    const abrirModalClientes = async () => {
        await cargarClientes();
        if (clientesModal) clientesModal.show();
    };

    const verImagen = (p) => {
      pagoSeleccionado.value = p;
      imagenSeleccionada.value = getUploadUrl(p.ruta_imagen);
      imagenModal.show();
    };

    const verHistorialCliente = async (cliente) => {
        clienteSeleccionado.value = cliente;
        pagosCliente.value = [];
        clienteTotales.total_bs = 0;
        clienteTotales.total_usd = 0;
        clienteTotales.total_pagos = 0;
        cargandoHistorialCliente.value = true;
        if (historialClienteModal) historialClienteModal.show();

        try {
            const res = await fetch(`/clientes/${cliente.id}/pagos`, { headers: getHeaders() });
            if (res.ok) {
                const data = await res.json();
                pagosCliente.value = data.pagos;
                clienteTotales.total_bs = data.total_bs || 0;
                clienteTotales.total_usd = data.total_usd || 0;
                clienteTotales.total_pagos = data.total_pagos || 0;
            } else {
                showToast('No se pudo cargar el historial del cliente', 'danger');
                if (historialClienteModal) historialClienteModal.hide();
            }
        } catch (e) {
            console.error('Error cargando historial cliente:', e);
            showToast('Error de red', 'danger');
            if (historialClienteModal) historialClienteModal.hide();
        } finally {
            cargandoHistorialCliente.value = false;
        }
    };

    const verHistorial = async (id) => {
        historial.value = [];
        cargandoHistorial.value = true;
        try {
            const res = await fetch(`/pago/${id}/historial`, { headers: getHeaders() });
            if (res.ok) {
                historial.value = await res.json();
                if (historialModal) historialModal.show();
            }
        } catch (e) { showToast('Error historial', 'danger'); }
        finally { cargandoHistorial.value = false; }
    };

    const reprocesar = async (p) => {
        if (!p.ruta_imagen) return;
        if (!confirm('¿Re-procesar imagen?')) return;
        try {
            showToast('Procesando...', 'info');
            const res = await fetch(`/reprocesar/${p.id}`, { method: 'POST', headers: getHeaders() });
            if (res.ok) {
                showToast('Lectura actualizada', 'success');
                cargar(page.value);
            } else { throw new Error('Error servidor'); }
        } catch (e) { showToast('Fallo al reprocesar', 'danger'); }
    };

    const confirmEliminar = async (p) => {
      if (!confirm(`¿Eliminar pago ${p.referencia}?`)) return;
      try {
        const res = await fetch(`/eliminar-pago-ref/${encodeURIComponent(p.referencia)}?confirm=true`, { method: 'DELETE', headers: getHeaders() });
        if (res.ok) {
            showToast('Eliminado', 'success');
            cargar(page.value);
        }
      } catch (e) { showToast('Error al eliminar', 'danger'); }
    };

    const subirPago = async () => {
        const form = document.getElementById('uploadForm');
        const errorDiv = document.getElementById('uploadError');
        if(!form || !errorDiv) return;

        errorDiv.classList.add('d-none');
        errorDiv.textContent = '';

        const input = form.querySelector('input[type=file]');
        if (!input.files.length) {
            errorDiv.textContent = 'Por favor, selecciona un archivo de imagen.';
            errorDiv.classList.remove('d-none');
            return;
        }
        
        const fd = new FormData(form);
        if (!fd.get('cliente_id')) fd.delete('cliente_id');

        procesandoSubida.value = true;
        try {
            const res = await fetch('/subir-pago/', { method: 'POST', body: fd, headers: getHeaders() });
            let r;
            try { r = await res.json(); } catch(e){ r = { mensaje: await res.text() }; }
            
            if (res.ok) {
                showToast(r.mensaje || 'Pago subido y procesado', 'success');
                uploadModal.hide();
                form.reset();
                uploadBank.value = '';
                cargar(0);
            } else {
                errorDiv.textContent = r.mensaje || r.detail || 'Ocurrió un error al procesar la imagen.';
                errorDiv.classList.remove('d-none');
            }
        } catch (e) {
            console.error(e);
            errorDiv.textContent = 'Error de conexión. Verifica tu red.';
            errorDiv.classList.remove('d-none');
        } finally {
            procesandoSubida.value = false;
        }
    };

    // --- Lifecycle ---
    onMounted(() => {
        console.log("✅ App montada (Composition API)");
        uploadModal = new bootstrap.Modal(document.getElementById('uploadModal'));
        manualModal = new bootstrap.Modal(document.getElementById('manualModal'));
        
        const hModalEl = document.getElementById('modalHistorial');
        if (hModalEl) historialModal = new bootstrap.Modal(hModalEl);
        
        imagenModal = new bootstrap.Modal(document.getElementById('imagenModal'));
        
        const cModalEl = document.getElementById('clientesModal');
        if (cModalEl) clientesModal = new bootstrap.Modal(cModalEl);

        const hcModalEl = document.getElementById('historialClienteModal');
        if (hcModalEl) historialClienteModal = new bootstrap.Modal(hcModalEl);

        cargarBancos();
        cargar(0);
        cargarReportes();
        cargarClientes(); // Cargar clientes al inicio
    });

    return {
        vistaActual, uploadBank, procesandoSubida,
        pagos, q, page, limit, total, totalPages, bancosDisponibles,
        manualItem, nuevoCliente, clientes,
        editandoCliente, qClientes,
        historial, cargandoHistorial, imagenSeleccionada, pagoSeleccionado, 
        calcBs, calcUsd, tasaActualCalc, conversionResult, bancoFiltro, reportPeriod, fechaInicio, fechaFin, reportes,
        clienteTotales,
        chatInput, chatHistory, cargandoChat, enviarConsultaIA,
        syncCalculadora, refrescarTasaCalculadora,
        clienteSeleccionado, pagosCliente, cargandoHistorialCliente,
        // Methods
        cargar, buscar, cargarReportes, exportarReporte, cargarBancos, formatMonto, formatNumero, formatDate, formatAccion,
        verImagen, reprocesar, verHistorial, confirmEliminar, subirPago,
        cargarClientes, abrirModalClientes, abrirModalSubida, abrirModalManual,
        agregarCliente, guardarManual, cambiarEstado, verHistorialCliente,
        prepararEdicion, guardarEdicion, eliminarCliente,
        promptApiKey, getUploadUrl
    };
  }
}).mount('#app');