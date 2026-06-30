from aiogram import Router, types
from config import ADMIN_IDS
from database import get_user

router = Router()


@router.message(lambda m: m.text == "🆘 Поддержка")
async def support_menu(message: types.Message):
    admin_list = []
    for admin_id in ADMIN_IDS:
        admin_user = await get_user(admin_id)
        if admin_user:
            if admin_user["username"]:
                admin_list.append(f"@{admin_user['username']}")
            else:
                admin_list.append(admin_user["first_name"])
        else:
            admin_list.append(str(admin_id))

    admin_text = ", ".join(admin_list)
    await message.answer(
        f"По вопросам и проблемам обращайтесь к администратору: {admin_text}\n\n"
        f"Опишите вашу проблему и администратор свяжется с вами."
    )
