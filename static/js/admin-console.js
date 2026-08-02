/* テナント・ユーザー管理画面。
   サーバは操作のたびに全体スナップショット（tenants / users / roles）を返すので、
   画面はそれを丸ごと描き直す。差分更新をやめて、表示と実データのズレを作らない。 */
(function () {
  'use strict';

  var API = '/api/admin/tenancy';
  var state = { tenants: [], users: [], roles: [], mock_auth: true };

  var alertBox = document.getElementById('adm-alert');
  var tenantRows = document.getElementById('tenant-rows');
  var userRows = document.getElementById('user-rows');
  var tenantSelect = document.getElementById('u-tenant');
  var modal = document.getElementById('membership-modal');
  var modalList = document.getElementById('membership-list');
  var modalSub = document.getElementById('membership-sub');
  var editingUserId = '';

  function showError(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
    alertBox.scrollIntoView({ block: 'nearest' });
  }

  function clearError() {
    alertBox.hidden = true;
    alertBox.textContent = '';
  }

  function request(method, path, body) {
    var options = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) options.body = JSON.stringify(body);
    return fetch(API + path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || '操作に失敗しました。');
        return data;
      });
    });
  }

  function apply(data) {
    if (data.tenants) state.tenants = data.tenants;
    if (data.users) state.users = data.users;
    if (data.roles) state.roles = data.roles;
    if (typeof data.mock_auth === 'boolean') state.mock_auth = data.mock_auth;
    render();
  }

  function run(promise, onDone) {
    clearError();
    promise.then(function (data) {
      apply(data);
      if (onDone) onDone(data);
    }).catch(function (error) {
      showError(error.message || String(error));
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function roleLabel(value) {
    for (var i = 0; i < state.roles.length; i += 1) {
      if (state.roles[i].value === value) return state.roles[i].label;
    }
    return value;
  }

  function actionButton(label, className, handler) {
    var button = el('button', 'btn-ghost' + (className ? ' ' + className : ''), label);
    button.type = 'button';
    button.addEventListener('click', handler);
    return button;
  }

  // --- 描画 -------------------------------------------------------------

  function renderTenants() {
    tenantRows.textContent = '';
    if (!state.tenants.length) {
      var empty = el('tr');
      var cell = el('td', 'adm-empty', 'テナントがありません。上のフォームから作成してください。');
      cell.colSpan = 5;
      empty.appendChild(cell);
      tenantRows.appendChild(empty);
      return;
    }
    state.tenants.forEach(function (tenant) {
      var row = el('tr');
      row.appendChild(el('td', 'cell-strong', tenant.name));
      row.appendChild(el('td', 'cell-mono', tenant.slug));
      row.appendChild(el('td', null, tenant.member_count));
      row.appendChild(el('td', 'cell-mono', String(tenant.created_at || '').slice(0, 10)));

      var actions = el('div', 'row-actions');
      actions.appendChild(actionButton('名前を変更', '', function () {
        var name = window.prompt('新しいテナント名', tenant.name);
        if (name === null) return;
        run(request('PATCH', '/tenants/' + tenant.id, { name: name }));
      }));
      actions.appendChild(actionButton('削除', 'is-danger', function () {
        var ok = window.confirm(
          'テナント「' + tenant.name + '」を削除します。\n' +
          '所属とAPIトークンも削除されます。\n' +
          'output/tenants/' + tenant.slug + ' 配下の生成物は残ります。'
        );
        if (!ok) return;
        run(request('DELETE', '/tenants/' + tenant.id), function (data) {
          if (data.note) showNote(data.note);
        });
      }));
      var actionCell = el('td');
      actionCell.appendChild(actions);
      row.appendChild(actionCell);
      tenantRows.appendChild(row);
    });
  }

  function showNote(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
  }

  function renderTenantOptions() {
    var previous = tenantSelect.value;
    tenantSelect.textContent = '';
    var none = el('option', null, '所属なし（後で割り当てる）');
    none.value = '';
    tenantSelect.appendChild(none);
    state.tenants.forEach(function (tenant) {
      var option = el('option', null, tenant.name);
      option.value = tenant.id;
      tenantSelect.appendChild(option);
    });
    tenantSelect.value = previous;
  }

  function renderUsers() {
    userRows.textContent = '';
    state.users.forEach(function (user) {
      var row = el('tr');
      if (!user.is_active) row.className = 'is-inactive';

      var nameCell = el('td', 'cell-strong', user.name);
      if (!user.is_active) nameCell.appendChild(el('span', 'badge-inactive', '無効'));
      row.appendChild(nameCell);
      row.appendChild(el('td', 'cell-mono', user.email));

      var membershipCell = el('td');
      if (user.memberships.length) {
        user.memberships.forEach(function (membership) {
          var chip = el(
            'span',
            'chip' + (membership.role === 'admin' ? ' is-admin' : ''),
            membership.name + ' / ' + roleLabel(membership.role)
          );
          membershipCell.appendChild(chip);
        });
      } else {
        membershipCell.appendChild(el('span', 'cell-warn', '所属なし（割り当て待ち）'));
      }
      row.appendChild(membershipCell);

      var actions = el('div', 'row-actions');
      actions.appendChild(actionButton('所属を編集', '', function () {
        openMembershipModal(user);
      }));
      if (user.memberships.length) {
        actions.appendChild(actionButton(user.is_active ? '無効化' : '有効化', user.is_active ? 'is-danger' : '', function () {
          run(request('PATCH', '/users/' + user.id, { is_active: !user.is_active }));
        }));
      } else {
        actions.appendChild(actionButton('削除', 'is-danger', function () {
          if (!window.confirm('ユーザー「' + user.name + '」を削除します。')) return;
          run(request('DELETE', '/users/' + user.id));
        }));
      }
      var actionCell = el('td');
      actionCell.appendChild(actions);
      row.appendChild(actionCell);
      userRows.appendChild(row);
    });
  }

  function render() {
    renderTenants();
    renderTenantOptions();
    renderUsers();
  }

  // --- 所属編集 ---------------------------------------------------------

  function openMembershipModal(user) {
    editingUserId = user.id;
    modalSub.textContent = user.name + '（' + user.email + '）';
    modalList.textContent = '';

    var assigned = {};
    user.memberships.forEach(function (membership) {
      assigned[membership.tenant_id] = membership.role;
    });

    state.tenants.forEach(function (tenant) {
      var line = el('label', 'adm-modal-row');
      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = tenant.id;
      checkbox.checked = Object.prototype.hasOwnProperty.call(assigned, tenant.id);

      var select = document.createElement('select');
      state.roles.forEach(function (role) {
        var option = el('option', null, role.label);
        option.value = role.value;
        select.appendChild(option);
      });
      select.value = assigned[tenant.id] || 'member';
      select.disabled = !checkbox.checked;
      checkbox.addEventListener('change', function () {
        select.disabled = !checkbox.checked;
      });

      line.appendChild(checkbox);
      var text = el('span', 'adm-modal-name', tenant.name);
      text.appendChild(el('span', 'adm-modal-slug', tenant.slug));
      line.appendChild(text);
      line.appendChild(select);
      modalList.appendChild(line);
    });

    if (!state.tenants.length) {
      modalList.appendChild(el('p', 'adm-empty', 'テナントがありません。先にテナントを作成してください。'));
    }
    modal.hidden = false;
  }

  function closeModal() {
    modal.hidden = true;
    editingUserId = '';
  }

  document.getElementById('membership-save').addEventListener('click', function () {
    var entries = [];
    modalList.querySelectorAll('.adm-modal-row').forEach(function (line) {
      var checkbox = line.querySelector('input[type="checkbox"]');
      var select = line.querySelector('select');
      if (checkbox && checkbox.checked) {
        entries.push({ tenant_id: checkbox.value, role: select.value });
      }
    });
    run(request('PUT', '/users/' + editingUserId + '/memberships', { memberships: entries }), closeModal);
  });

  modal.addEventListener('click', function (event) {
    if (event.target === modal || event.target.hasAttribute('data-close')) closeModal();
  });

  // --- フォーム ---------------------------------------------------------

  document.getElementById('tenant-form').addEventListener('submit', function (event) {
    event.preventDefault();
    var name = document.getElementById('t-name');
    var slug = document.getElementById('t-slug');
    run(request('POST', '/tenants', { name: name.value, slug: slug.value }), function () {
      name.value = '';
      slug.value = '';
    });
  });

  document.getElementById('user-form').addEventListener('submit', function (event) {
    event.preventDefault();
    var name = document.getElementById('u-name');
    var email = document.getElementById('u-mail');
    var role = document.getElementById('u-role');
    var password = document.getElementById('u-password');
    run(request('POST', '/users', {
      name: name.value,
      email: email.value,
      tenant_id: tenantSelect.value,
      role: role.value,
      password: password.value
    }), function () {
      name.value = '';
      email.value = '';
      password.value = '';
    });
  });

  run(request('GET', ''));
})();
