const { createApp, ref, reactive, computed, onMounted, watch } = Vue;

createApp({
    data() {
        return {
            pagos: [],
            bancosDisponibles: [],
            clientes: [],
            reportes: [],
            pagoSeleccionado: null,
            historial: [],
            pagosCliente: [],
            clienteSeleccionado: null,
            clienteTotales: {},
            vistaActual: 'pagos',
            q: '',
            qClientes: '',
            page: 1,
            totalPages: 1,
            bancoFiltro: '',
            reportPeriod: 'mensual',
            fechaInicio: '',
            fechaFin: '',
            chatInput: '',
            chatHistory: [],
            cargandoChat: false,
            showUploadModal: false,
            showManualModal: false,
            showImagenModal: false,
            showHistorialModal: false,
            showHistorialClienteModal: false,
            showNuevoClienteModal: false,
            showEditarClienteModal: false,
            editandoCliente: null,
            uploadBank: '',
            uploadError: '',
            uploadFileSelected: false,
            procesandoSubida: false,
            manualItem: {
                banco: '',
                referencia: '',
                monto: 0,
                cliente_id: null,
            },
            nuevoCliente: {
                nombre: '',
                cedula: '',
                telefono: '',
            },
            editandoPagoId: null,
            activeEstadoMenu: null,
            imagenSeleccionada: '',
            tasaActualCalc: 0,
            calcBs: 0,
            calcUsd: 0,
            cargandoHistorial: false,
            cargandoHistorialCliente: false,
            showGestionModal: false,
            gestionTab: 'ia',
            gestionState: 'offline',
            gestionApiKey: '',
            gestionDbInfo: '',
            gestionDbMessage: '',
            gestionAdminUser: '',
            gestionAdminPass: '',
            gestionClientesTotal: 0,
            gestionUltimosClientes: [],
        };
    },
    computed: {
        filteredPagos() {
            let pagos = this.pagos;
            if (this.bancoFiltro) {
                pagos = pagos.filter((p) => p.banco === this.bancoFiltro);
            }
            if (this.q) {
                pagos = pagos.filter((p) => p.referencia.toLowerCase().includes(this.q.toLowerCase()));
            }
            return pagos;
        },
    },
    methods: {
        async cargar(page = 1) {
            if (page < 1) {
                page = 1;
            }
            this.page = page;
            try {
                const resp = await fetch(`/pagos/?page=${page}&banco=${encodeURIComponent(this.bancoFiltro)}&q=${encodeURIComponent(this.q)}`);
                const data = await resp.json();
                this.pagos = data.items || [];
                this.totalPages = data.pages || 1;
                if (!this.bancosDisponibles.length && data.bancos) {
                    this.bancosDisponibles = data.bancos;
                }
            } catch (err) {
                this.showToast('Error al cargar pagos', 'danger');
            }
        },
        async cargarClientes() {
            try {
                const resp = await fetch(`/clientes/?q=${encodeURIComponent(this.qClientes)}`);
                const data = await resp.json();
                this.clientes = Array.isArray(data) ? data : data.clientes || [];
            } catch (err) {
                this.showToast('Error al cargar clientes', 'danger');
            }
        },
        async cargarReportes() {
            try {
                const params = new URLSearchParams();
                params.set('tipo_reporte', this.reportPeriod);
                if (this.fechaInicio) params.set('start_date', this.fechaInicio);
                if (this.fechaFin) params.set('end_date', this.fechaFin);
                const resp = await fetch(`/reportes/?${params.toString()}`);
                const data = await resp.json();
                this.reportes = data.resultados || [];
            } catch (err) {
                this.showToast('Error al cargar reportes', 'danger');
            }
        },
        buscar() {
            this.cargar(1);
        },
        async exportarReporte(formato) {
            const params = new URLSearchParams();
            params.set('tipo_reporte', this.reportPeriod);
            params.set('format', formato);
            if (this.fechaInicio) params.set('start_date', this.fechaInicio);
            if (this.fechaFin) params.set('end_date', this.fechaFin);
            const url = `/reportes/export/?${params.toString()}`;
            try {
                const resp = await fetch(url);
                if (!resp.ok) {
                    throw new Error('No se pudo exportar el reporte');
                }
                const blob = await resp.blob();
                const filename = resp.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || `reporte.${formato}`;
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
            } catch (err) {
                this.showToast('Error al exportar reporte', 'danger');
            }
        },
        async refrescarTasaCalculadora() {
            try {
                const resp = await fetch(`/tasa-bcv/`);
                const data = await resp.json();
                this.tasaActualCalc = data.tasa_bcv || 0;
            } catch (err) {
                this.showToast('No se pudo obtener la tasa.', 'danger');
            }
        },
        syncCalculadora(type) {
            if (!this.tasaActualCalc || this.tasaActualCalc === 0) return;
            if (type === 'bs') {
                this.calcUsd = parseFloat((this.calcBs / this.tasaActualCalc).toFixed(2));
            } else {
                this.calcBs = parseFloat((this.calcUsd * this.tasaActualCalc).toFixed(2));
            }
        },
        async enviarConsultaIA() {
            if (!this.chatInput.trim()) return;
            const pregunta = this.chatInput.trim();
            this.chatHistory.push({ role: 'user', content: pregunta });
            this.chatInput = '';
            this.cargandoChat = true;
            try {
                const resp = await fetch('/IA/consultar/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pregunta }),
                });
                const data = await resp.json();
                this.chatHistory.push({ role: 'assistant', content: data.respuesta || 'No hubo respuesta.' });
                this.$nextTick(() => {
                    const chatWindow = document.getElementById('chatWindow');
                    if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
                });
            } catch (err) {
                this.showToast('Error al consultar IA', 'danger');
            } finally {
                this.cargandoChat = false;
            }
        },
        async abrirModalSubida() {
            if (!this.bancosDisponibles.length) {
                await this.cargarBancos();
            }
            this.uploadError = '';
            this.uploadBank = '';
            this.uploadFileSelected = false;
            this.showUploadModal = true;
        },
        onUploadFileChange(event) {
            this.uploadFileSelected = event.target.files && event.target.files.length > 0;
        },
        closeUploadModal() {
            this.showUploadModal = false;
            this.uploadError = '';
            this.uploadFileSelected = false;
        },
        abrirModalManual() {
            this.editandoPagoId = null;
            this.manualItem = { banco: '', referencia: '', monto: 0, cliente_id: null };
            this.showManualModal = true;
        },
        editarPago(pago) {
            this.editandoPagoId = pago.id;
            this.manualItem = {
                banco: pago.banco || '',
                referencia: pago.referencia || '',
                monto: pago.monto || 0,
                cliente_id: pago.cliente_id || null,
            };
            this.showManualModal = true;
        },
        closeManualModal() {
            this.showManualModal = false;
            this.editandoPagoId = null;
        },
        async subirPago() {
            const formEl = document.getElementById('uploadForm');
            const formData = new FormData(formEl);
            if (!formData.get('file')) {
                this.uploadError = 'Seleccione un archivo de imagen.';
                return;
            }
            if (!this.uploadBank) {
                this.uploadError = 'Seleccione un banco.';
                return;
            }
            formData.set('banco', this.uploadBank);
            this.procesandoSubida = true;
            try {
                if (!formData.get('cliente_id')) {
                formData.delete('cliente_id');
            }
            const resp = await fetch('/subir-pago/', {
                    method: 'POST',
                    headers: this.getAuthHeaders(),
                    body: formData,
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Pago subido y procesado', 'success');
                    this.closeUploadModal();
                    await this.cargar(this.page);
                } else {
                    this.uploadError = data.detail || data.error || data.message || 'Error al subir pago.';
                }
            } catch (err) {
                this.uploadError = 'Error de red al subir pago.';
            } finally {
                this.procesandoSubida = false;
            }
        },
        async guardarManual() {
            if (!this.manualItem.banco) {
                this.showToast('Falta el banco: selecciona uno de la lista para poder registrar el pago manual.', 'warning');
                return;
            }
            if (!this.manualItem.referencia || !this.manualItem.referencia.trim()) {
                this.showToast('Falta la referencia: ingresa una referencia válida para el pago.', 'warning');
                return;
            }
            if (!/^[0-9]+$/.test(this.manualItem.referencia.trim())) {
                this.showToast('La referencia debe contener solo números.', 'warning');
                return;
            }
            if (!this.manualItem.monto || this.manualItem.monto <= 0) {
                this.showToast('Monto inválido: ingresa un valor numérico mayor a cero.', 'warning');
                return;
            }

            const url = this.editandoPagoId ? `/pagos/${this.editandoPagoId}` : '/pago-manual/';
            const method = this.editandoPagoId ? 'PATCH' : 'POST';

            try {
                const resp = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.manualItem),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(this.editandoPagoId ? 'Pago manual actualizado' : 'Pago manual guardado', 'success');
                    this.closeManualModal();
                    this.cargar(this.page);
                } else {
                    this.showToast(data.detail || data.error || 'Error al guardar pago manual', 'danger');
                }
            } catch (err) {
                this.showToast('Error al guardar pago manual', 'danger');
            }
        },
        async openNuevoClienteModal() {
            this.nuevoCliente = { nombre: '', cedula: '', telefono: '' };
            this.showNuevoClienteModal = true;
        },
        closeNuevoClienteModal() {
            this.showNuevoClienteModal = false;
        },
        async agregarCliente() {
            if (!this.nuevoCliente.nombre || !this.nuevoCliente.nombre.trim()) {
                this.showToast('El nombre es obligatorio', 'warning');
                return;
            }
            if (!this.nuevoCliente.cedula || !this.nuevoCliente.cedula.trim()) {
                this.showToast('La cédula es obligatoria', 'warning');
                return;
            }
            if (!/^[0-9]+$/.test(this.nuevoCliente.cedula.trim())) {
                this.showToast('La cédula debe contener solo números.', 'warning');
                return;
            }
            if (this.nuevoCliente.telefono && !/^[0-9]+$/.test(this.nuevoCliente.telefono.trim())) {
                this.showToast('El teléfono debe contener solo números.', 'warning');
                return;
            }
            try {
                const resp = await fetch('/clientes/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.nuevoCliente),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Cliente agregado', 'success');
                    this.closeNuevoClienteModal();
                    this.cargarClientes();
                } else {
                    this.showToast(data.detail || data.error || 'Error al agregar cliente', 'danger');
                }
            } catch (err) {
                this.showToast('Error al agregar cliente', 'danger');
            }
        },
        prepararEdicion(cliente) {
            this.editandoCliente = { ...cliente };
            this.showEditarClienteModal = true;
        },
        closeEditarClienteModal() {
            this.showEditarClienteModal = false;
            this.editandoCliente = null;
        },
        async guardarEdicion() {
            if (!this.editandoCliente) return;
            if (!this.editandoCliente.cedula || !this.editandoCliente.cedula.trim()) {
                this.showToast('La cédula es obligatoria', 'warning');
                return;
            }
            if (!/^[0-9]+$/.test(this.editandoCliente.cedula.trim())) {
                this.showToast('La cédula debe contener solo números.', 'warning');
                return;
            }
            if (this.editandoCliente.telefono && !/^[0-9]+$/.test(this.editandoCliente.telefono.trim())) {
                this.showToast('El teléfono debe contener solo números.', 'warning');
                return;
            }
            try {
                const resp = await fetch(`/clientes/${this.editandoCliente.id}/`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.editandoCliente),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Cliente actualizado', 'success');
                    this.closeEditarClienteModal();
                    this.cargarClientes();
                } else {
                    this.showToast(data.error || 'Error al actualizar cliente', 'danger');
                }
            } catch (err) {
                this.showToast('Error al actualizar cliente', 'danger');
            }
        },
        async eliminarCliente(id) {
            if (!confirm('¿Eliminar este cliente?')) return;
            try {
                const resp = await fetch(`/clientes/${id}/`, { method: 'DELETE' });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Cliente eliminado', 'success');
                    this.cargarClientes();
                } else {
                    this.showToast(data.error || 'Error al eliminar cliente', 'danger');
                }
            } catch (err) {
                this.showToast('Error al eliminar cliente', 'danger');
            }
        },
        async verPago(pago) {
            this.pagoSeleccionado = pago;
            this.imagenSeleccionada = '';
            if (pago.ruta_imagen) {
                try {
                    const resp = await fetch(`/pagos/${pago.id}/imagen`);
                    if (resp.ok) {
                        const data = await resp.json();
                        this.imagenSeleccionada = data.imagen_url;
                    }
                } catch (err) {
                    this.showToast('No se pudo cargar la imagen', 'danger');
                }
            }
            this.showImagenModal = true;
        },
        async verHistorial(pagoId) {
            this.showHistorialModal = true;
            this.cargandoHistorial = true;
            try {
                const resp = await fetch(`/pago/${pagoId}/historial`);
                const data = await resp.json();
                this.historial = data || [];
            } catch (err) {
                this.showToast('Error al cargar historial', 'danger');
            } finally {
                this.cargandoHistorial = false;
            }
        },
        closeImagenModal() {
            this.showImagenModal = false;
            this.pagoSeleccionado = null;
            this.imagenSeleccionada = '';
        },
        closeHistorialModal() {
            this.showHistorialModal = false;
            this.historial = [];
        },
        async verHistorialCliente(cliente) {
            this.clienteSeleccionado = cliente;
            this.showHistorialClienteModal = true;
            this.cargandoHistorialCliente = true;
            try {
                const resp = await fetch(`/clientes/${cliente.id}/pagos`);
                const data = await resp.json();
                this.pagosCliente = data.pagos || [];
                this.clienteTotales = {
                    total_bs: data.total_bs || 0,
                    total_usd: data.total_usd || 0,
                    total_pagos: data.total_pagos || 0,
                };
            } catch (err) {
                this.showToast('Error al cargar historial del cliente', 'danger');
            } finally {
                this.cargandoHistorialCliente = false;
            }
        },
        closeHistorialClienteModal() {
            this.showHistorialClienteModal = false;
            this.clienteSeleccionado = null;
            this.pagosCliente = [];
        },
        toggleEstadoMenu(id) {
            this.activeEstadoMenu = this.activeEstadoMenu === id ? null : id;
        },
        async cambiarEstado(id, estado) {
            try {
                const resp = await fetch(`/pago/${id}/estado`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ estado }),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Estado actualizado', 'success');
                    this.cargar(this.page);
                } else {
                    this.showToast(data.error || 'No se pudo actualizar el estado', 'danger');
                }
            } catch (err) {
                this.showToast('Error al actualizar estado', 'danger');
            } finally {
                this.activeEstadoMenu = null;
            }
        },
        async reprocesar(pago) {
            try {
                const resp = await fetch(`/reprocesar/${pago.id}`, { method: 'POST' });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Reprocesado solicitado', 'success');
                    this.cargar(this.page);
                } else {
                    this.showToast(data.error || 'Error al reprocesar', 'danger');
                }
            } catch (err) {
                this.showToast('Error al reprocesar pago', 'danger');
            }
        },
        async confirmEliminar(pago) {
            if (!confirm('Eliminar pago seleccionado?')) return;
            try {
                const resp = await fetch(`/pagos/${pago.id}/`, { method: 'DELETE' });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast('Pago eliminado', 'success');
                    this.cargar(this.page);
                } else {
                    this.showToast(data.error || 'Error al eliminar pago', 'danger');
                }
            } catch (err) {
                this.showToast('Error al eliminar pago', 'danger');
            }
        },
        showToast(message, variant = 'info') {
            const toast = document.createElement('div');
            toast.className = `toast toast-${variant}`;
            toast.textContent = message;
            document.getElementById('toastContainer').appendChild(toast);
            setTimeout(() => {
                toast.classList.add('visible');
            }, 50);
            setTimeout(() => {
                toast.classList.remove('visible');
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        },
        formatMonto(value) {
            if (value == null) return '0.00';
            return Number(value).toLocaleString('es-VE', { style: 'currency', currency: 'VES' });
        },
        formatNumero(value) {
            if (value == null) return '0.00';
            return Number(value).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },
        formatDate(value) {
            if (!value) return '';
            return new Date(value).toLocaleDateString('es-VE');
        },
        estadoTexto(estado) {
            if (estado === 'verificado') return 'Verificado';
            if (estado === 'falso') return 'Falso';
            return 'No Verificado';
        },
        formatAccion(accion) {
            const mapping = {
                cambio_estado: 'Cambio de estado',
                actualización: 'Actualización',
                registro: 'Registro',
            };
            return mapping[accion] || accion;
        },
        async abrirGestion() {
            this.showGestionModal = true;
            this.gestionTab = 'ia';
            await this.cargarGestionStatus();
            await this.cargarCredenciales();
            await this.cargarGestionClientesSummary();
        },
        closeGestionModal() {
            this.showGestionModal = false;
        },
        async cargarGestionStatus() {
            try {
                const resp = await fetch('/gestion/ia/status');
                const data = await resp.json();
                this.gestionState = data.state || 'offline';
                this.gestionApiKey = data.api_key || '';
            } catch (err) {
                this.showToast('No se pudo leer el estado de IA', 'warning');
            }
            try {
                const resp = await fetch('/gestion/db/status');
                const data = await resp.json();
                this.gestionDbInfo = data.info || data.database_type || data.path || 'No disponible';
                this.gestionDbMessage = data.message || '';
            } catch (err) {
                this.gestionDbInfo = '';
                this.gestionDbMessage = 'No se pudo leer el estado de la base de datos.';
            }
        },
        async cargarCredenciales() {
            try {
                const resp = await fetch('/gestion/db/credentials');
                const data = await resp.json();
                this.gestionAdminUser = data.admin_user || '';
                this.gestionAdminPass = data.admin_pass || '';
            } catch (err) {
                this.showToast('No se pudo cargar las credenciales', 'warning');
            }
        },
        async guardarGestionApiKey() {
            if (!this.gestionApiKey.trim()) {
                this.showToast('Debes ingresar una clave Groq válida', 'warning');
                return;
            }
            try {
                const resp = await fetch('/gestion/ia/key', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: this.gestionApiKey.trim() }),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(data.mensaje || 'Clave Groq guardada', 'success');
                    this.gestionState = 'online';
                } else {
                    this.showToast(data.detail || 'No se pudo guardar la clave Groq', 'danger');
                }
            } catch (err) {
                this.showToast('Error al guardar la clave Groq', 'danger');
            }
        },
        async exportarPagosCsv() {
            try {
                const resp = await fetch('/gestion/db/export-pagos');
                if (!resp.ok) throw new Error('No se pudo exportar pagos.');
                const blob = await resp.blob();
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = 'pagos_export.csv';
                document.body.appendChild(link);
                link.click();
                link.remove();
                this.showToast('Pagos exportados', 'success');
            } catch (err) {
                this.showToast(err.message || 'Error al exportar pagos', 'danger');
            }
        },
        async importarPagosCsv(event) {
            const file = event.target.files?.[0];
            if (!file) return;
            if (!file.name.toLowerCase().endsWith('.csv')) {
                this.showToast('Solo se permiten archivos .csv', 'warning');
                return;
            }
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/gestion/db/import-pagos', {
                    method: 'POST',
                    body: formData,
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(data.mensaje || 'Pagos importados', 'success');
                } else {
                    this.showToast(data.detail || 'Error al importar pagos', 'danger');
                }
            } catch (err) {
                this.showToast('Error al importar pagos', 'danger');
            } finally {
                event.target.value = '';
            }
        },
        async limpiarDatosPrueba() {
            if (!confirm('Deseas borrar los pagos de prueba y no verificados?')) return;
            try {
                const resp = await fetch('/gestion/db/clear-test-data', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(data.mensaje || 'Datos de prueba eliminados', 'success');
                } else {
                    this.showToast(data.detail || 'Error al limpiar datos', 'danger');
                }
            } catch (err) {
                this.showToast('Error al limpiar datos de prueba', 'danger');
            }
        },
        async guardarCredenciales() {
            if (!this.gestionAdminUser.trim() || !this.gestionAdminPass.trim()) {
                this.showToast('Usuario y contraseña admin son obligatorios', 'warning');
                return;
            }
            try {
                const resp = await fetch('/gestion/db/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_user: this.gestionAdminUser.trim(), admin_pass: this.gestionAdminPass.trim() }),
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(data.mensaje || 'Credenciales guardadas', 'success');
                } else {
                    this.showToast(data.detail || 'Error al guardar credenciales', 'danger');
                }
            } catch (err) {
                this.showToast('Error al guardar credenciales', 'danger');
            }
        },
        async exportarClientesCsv() {
            try {
                const resp = await fetch('/gestion/clientes/export');
                if (!resp.ok) throw new Error('No se pudo exportar clientes.');
                const blob = await resp.blob();
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = 'clientes_export.csv';
                document.body.appendChild(link);
                link.click();
                link.remove();
                this.showToast('Clientes exportados', 'success');
            } catch (err) {
                this.showToast(err.message || 'Error al exportar clientes', 'danger');
            }
        },
        async importarClientes(event) {
            const file = event.target.files?.[0];
            if (!file) return;
            if (!file.name.toLowerCase().endsWith('.csv')) {
                this.showToast('Solo se permiten archivos .csv', 'warning');
                return;
            }
            const formData = new FormData();
            formData.append('archivo', file);
            try {
                const resp = await fetch('/gestion/clientes/import', {
                    method: 'POST',
                    body: formData,
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.showToast(data.mensaje || 'Clientes importados', 'success');
                    await this.cargarGestionClientesSummary();
                } else {
                    this.showToast(data.detail || 'Error al importar clientes', 'danger');
                }
            } catch (err) {
                this.showToast('Error al importar clientes', 'danger');
            } finally {
                event.target.value = '';
            }
        },
        async cargarGestionClientesSummary() {
            try {
                const resp = await fetch('/gestion/clientes/summary');
                const data = await resp.json();
                this.gestionClientesTotal = data.total || 0;
                this.gestionUltimosClientes = data.ultimos || [];
            } catch (err) {
                this.showToast('No se pudo cargar el resumen de clientes', 'warning');
            }
        },
        promptApiKey() {
            this.abrirGestion();
        },
        getAuthHeaders() {
            const apiKey = localStorage.getItem('apiKeyConciliacion');
            return apiKey ? { 'x-api-key': apiKey } : {};
        },
        async cargarBancos() {
            try {
                const resp = await fetch('/bancos/');
                const data = await resp.json();
                this.bancosDisponibles = data.bancos || [];
            } catch (err) {
                this.showToast('Error al cargar bancos', 'danger');
            }
        },
    },
    mounted() {
        this.cargar(1);
        this.cargarClientes();
        this.cargarReportes();
        this.refrescarTasaCalculadora();
        this.cargarBancos();
    },
}).mount('#app');
