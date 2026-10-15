# Copyright 2017-2020 Tecnativa - Pedro M. Baeza
# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, exceptions
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class DynamicListCase(BaseCommon):
    # 19.0's BaseCommon.setup_independent_user() returned None, so these tests
    # ran as the superuser and needed no groups. 20.0 creates a real internal
    # user from `_test_user_groups`, which defaults to ('base.group_user',) --
    # and a plain internal user cannot write mailing.mailing, so
    # test_resend_process died on
    # `AccessError: You are not allowed to modify 'Mass Mailing'`.
    #
    # Declaring the group is the 20.0 hook for this, and it is a better test
    # than the 19.0 superuser run was: resending is a mass-mailing user's
    # action, so exercising it as one is what the module actually promises.
    _test_user_groups = ("base.group_user", "mass_mailing.group_mass_mailing_user")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.list = cls.env["mailing.list"].create({"name": "Test list"})
        cls.contact1 = cls.env["mailing.contact"].create(
            {
                "name": "Contact 1",
                "email": "email1@test.com",
                "list_ids": [Command.set([cls.list.id])],
            }
        )
        cls.contact2 = cls.env["mailing.contact"].create(
            {
                "name": "Contact 2",
                "email": "email2@test.com",
                "list_ids": [Command.set([cls.list.id])],
            }
        )
        # No "name": 20.0 dropped `utm.source.mixin` from mailing.mailing's
        # _inherit, and that mixin is where `name` came from -- it was
        # `related="source_id.name"`, so creating with it now raises
        # `ValueError: Invalid field 'name' in 'mailing.mailing'`. Nothing is
        # lost: `subject` below is the _rec_name and the only one asserted on,
        # and `source_id` survives as a real field that 20.0 computes a default
        # for. The mixin itself no longer exists anywhere in 20.0.
        cls.mass_mailing = cls.env["mailing.mailing"].create(
            {
                "email_from": "test@example.org",
                "mailing_model_id": cls.env.ref("mass_mailing.model_mailing_list").id,
                "contact_list_ids": [Command.set(cls.list.ids)],
                "subject": "Mailing test",
            }
        )
        # NOT .sudo() here. A class-level recordset is rebound to the test
        # method's env before each test, and that rebinding drops the su flag,
        # so a sudo() applied in setUpClass is silently gone by the time the
        # test runs -- `AccessError: You are not allowed to modify 'Scheduled
        # Action' (ir.cron)`. Harmless on 19.0, where BaseCommon ran everything
        # as superuser anyway. Sudo at the call site instead.
        cls.mm_cron = cls.env.ref("mass_mailing.ir_cron_mass_mailing_queue")

    def test_resend_error(self):
        with self.assertRaises(exceptions.UserError):
            self.mass_mailing.button_draft()

    def _mailing_action_done(self):
        self.mass_mailing.action_launch()
        with self.enter_registry_test_mode():
            self.mm_cron.sudo().method_direct_trigger()

    def test_resend_process(self):
        # Send mailing
        self._mailing_action_done()
        self.assertEqual(self.mass_mailing.state, "done")
        self.assertEqual(len(self.mass_mailing.mailing_trace_ids), 2)
        # Simulate that an email has not been sent
        self.mass_mailing.mailing_trace_ids.filtered(
            lambda x: x.email == self.contact2.email
        ).unlink()
        self.assertEqual(len(self.mass_mailing.mailing_trace_ids), 1)
        # Back to draft
        self.mass_mailing.button_draft()
        self.assertEqual(self.mass_mailing.state, "draft")
        # Send mailing again (already sent not sent again)
        self._mailing_action_done()
        self.assertEqual(self.mass_mailing.state, "done")
        self.assertEqual(len(self.mass_mailing.mailing_trace_ids), 2)
