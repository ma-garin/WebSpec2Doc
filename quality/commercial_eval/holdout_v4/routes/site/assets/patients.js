/* 患者の登録・検索 (IIFE) */
(function () {
  "use strict";

  var PATIENT_API = API_BASE + "/patients";
  var JSON_HEADERS = { "Content-Type": "application/json" };

  // 旧実装: fetch(API_BASE + "/patients/legacy-search") は v2.0 で廃止した

  function searchPatients(keyword) {
    return fetch(PATIENT_API + "?keyword=" + encodeURIComponent(keyword)).then(function (r) {
      return r.json();
    });
  }

  function loadPatient(patientId) {
    return fetch(PATIENT_API + "/" + patientId).then(function (r) {
      return r.json();
    });
  }

  function loadVisitHistory(patientId) {
    var url = PATIENT_API + "/" + patientId + "/visits";
    return fetch(url);
  }

  function registerPatient(form) {
    return fetch(PATIENT_API, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(form),
    });
  }

  function replaceInsurance(patientId, insurance) {
    return fetch(`${PATIENT_API}/${patientId}/insurance`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(insurance),
    });
  }

  function patchContact(patientId, contact) {
    return fetch(PATIENT_API + "/" + patientId + "/contact", {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(contact),
    });
  }

  function deletePatient(patientId) {
    return fetch(`${PATIENT_API}/${patientId}`, { method: "DELETE" });
  }

  // 保険番号を画面モデルから取り出すための JSON ポインタ (URL ではない)
  var INSURANCE_NUMBER_PTR = "/patient/insurance/number";
  function pick(model, pointer) {
    return pointer
      .split("/")
      .filter(Boolean)
      .reduce(function (acc, key) {
        return acc == null ? acc : acc[key];
      }, model);
  }

  window.PatientApp = {
    search: searchPatients,
    load: loadPatient,
    visits: loadVisitHistory,
    register: registerPatient,
    replaceInsurance: replaceInsurance,
    patchContact: patchContact,
    remove: deletePatient,
    insuranceNumberOf: function (model) {
      return pick(model, INSURANCE_NUMBER_PTR);
    },
  };
})();
