#!/usr/bin/env python3
"""
Проверка: есть ли CUDA и использует ли PyTorch GPU.
Запуск: python check_cuda.py
"""
import sys

def main():
    print("=== Проверка CUDA и PyTorch ===\n")
    try:
        import torch
    except ImportError:
        print("PyTorch не установлен. Установите: pip install -r requirements.txt")
        sys.exit(1)
    except OSError as e:
        if "126" in str(e) or "dll" in str(e).lower() or "dependencies" in str(e).lower():
            print("PyTorch (CUDA) установлен, но не загружается из-за отсутствующей DLL.")
            print("Часто помогает:")
            print("  1. Установить Microsoft Visual C++ Redistributable (64-bit):")
            print("     https://aka.ms/vs/17/release/vc_redist.x64.exe")
            print("  2. Перезапустить терминал/IDE и запустить проверку снова.")
            print("\nОшибка:", e)
        else:
            print("Ошибка загрузки PyTorch:", e)
        sys.exit(1)

    print(f"PyTorch: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA доступна: {cuda_available}")

    if cuda_available:
        print(f"Версия CUDA (в PyTorch): {torch.version.cuda}")
        print(f"Количество GPU: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            name = torch.cuda.get_device_name(i)
            mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
            print(f"  GPU {i}: {name} ({mem:.1f} GB)")
        print("\nТранскрипция будет выполняться на GPU (быстрее).")
    else:
        print("Версия CUDA в сборке PyTorch: нет (установлена CPU-версия).")
        print("\nЧтобы использовать видеокарту NVIDIA:")
        print("  1. Активируйте окружение: .venv\\Scripts\\activate")
        print("  2. Установите PyTorch с CUDA 12.4:")
        print("     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124")
        print("  3. Запустите этот скрипт снова.")
        sys.exit(1)
    return 0

if __name__ == "__main__":
    sys.exit(main())
