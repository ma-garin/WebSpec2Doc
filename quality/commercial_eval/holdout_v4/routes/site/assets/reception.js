/* 受付窓口の操作 (オブジェクトのメソッドから API を呼ぶ形) */
const ReceptionDesk = {
  queueUrl: QUEUE_BASE,

  checkIn(patientId, deptId) {
    return apiPost("/reception/check-in", { patientId: patientId, deptId: deptId });
  },

  callNext() {
    return fetch(this.queueUrl + "/next", { method: "POST" });
  },

  cancelTicket(ticketNo) {
    return req("DELETE", QUEUE_BASE + "/" + ticketNo);
  },

  raisePriority(ticketNo) {
    return apiSend("PUT", "/reception/queue/" + ticketNo + "/priority");
  },

  refreshQueue() {
    return getJson("/reception/queue");
  },

  loadDepartments() {
    return fetch(DEPT_URL);
  },

  loadDoctors() {
    return loadList("doctors");
  },

  loadSchedule(doctorId) {
    return fetch(`${API_BASE}/doctors/${doctorId}/schedule?week=current`);
  },

  assignRoom(doctorId, roomId) {
    return fetch(`${API_BASE}/doctors/${doctorId}/rooms/${roomId}/assign`, { method: "POST" });
  },
};
